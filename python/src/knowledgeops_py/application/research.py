"""Durable LangGraph Deep Research orchestration over Java-compatible workflow records."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from knowledgeops_py.domain.context import TenantContext
from knowledgeops_py.infrastructure.workflow_repository import SqlAlchemyWorkflowRepository

ResearchPlanner = Callable[[str], Awaitable[list[str]]]
ResearchRetriever = Callable[[str, str], Awaitable[dict[str, Any]]]
ResearchWriter = Callable[[str, list[dict[str, Any]]], Awaitable[str]]


class ResearchWorkflowState(TypedDict, total=False):
    task_id: str
    phase: str
    report: str


@dataclass(frozen=True, slots=True)
class ResearchRunResult:
    task: dict[str, Any]
    topic: str
    report: str


class ResearchNotResumable(ValueError):
    """The task is terminal or does not contain a recoverable research checkpoint."""


@dataclass(slots=True)
class DeepResearchApplicationService:
    """Persists each plan, retrieval, evidence-judge, and report-writing boundary."""

    repository: SqlAlchemyWorkflowRepository

    async def run(
        self,
        context: TenantContext,
        topic: str,
        model_profile: str,
        planner: ResearchPlanner,
        retriever: ResearchRetriever,
        writer: ResearchWriter,
    ) -> ResearchRunResult:
        task = await self.repository.start_task(
            context.tenant_id,
            "DEEP_RESEARCH",
            topic,
            model_profile,
            "",
            None,
        )
        return await self._execute(context, task, planner, retriever, writer)

    async def resume(
        self,
        context: TenantContext,
        task_id: str,
        planner: ResearchPlanner,
        retriever: ResearchRetriever,
        writer: ResearchWriter,
    ) -> ResearchRunResult:
        task = await self.repository.get(context.tenant_id, task_id)
        if task is None or task["type"] != "DEEP_RESEARCH" or task["status"] in {"DONE", "FAILED", "CANCELLED"}:
            raise ResearchNotResumable("research task cannot be resumed")
        return await self._execute(context, task, planner, retriever, writer)

    async def cancel(self, context: TenantContext, task_id: str) -> dict[str, Any] | None:
        task = await self.repository.get(context.tenant_id, task_id)
        if task is None or task["type"] != "DEEP_RESEARCH":
            return None
        if task["status"] in {"DONE", "FAILED", "CANCELLED"}:
            raise ResearchNotResumable("research task is already terminal")
        return await self.repository.cancel_task(context.tenant_id, task_id)

    async def _execute(
        self,
        context: TenantContext,
        task: dict[str, Any],
        planner: ResearchPlanner,
        retriever: ResearchRetriever,
        writer: ResearchWriter,
    ) -> ResearchRunResult:
        checkpoint = await self.repository.state(context.tenant_id, str(task["taskId"])) or {}
        state: ResearchWorkflowState = {
            "task_id": str(task["taskId"]),
            "phase": str(checkpoint.get("phase") or "planning"),
        }
        if isinstance(checkpoint.get("report"), str):
            state["report"] = checkpoint["report"]
        try:
            result = await self._graph(context, planner, retriever, writer).ainvoke(state)
        except Exception as exc:
            await self.repository.fail_task(context.tenant_id, str(task["taskId"]), str(exc))
            raise
        completed = await self.repository.require(context.tenant_id, str(task["taskId"]))
        report = result.get("report")
        if not isinstance(report, str):
            completed_state = await self.repository.state(context.tenant_id, str(task["taskId"])) or {}
            report = str(completed_state.get("report") or "")
        if not report:
            raise ResearchNotResumable("research report checkpoint is missing")
        return ResearchRunResult(completed, str(completed["userInput"]), report)

    def _graph(
        self,
        context: TenantContext,
        planner: ResearchPlanner,
        retriever: ResearchRetriever,
        writer: ResearchWriter,
    ) -> Any:
        graph = StateGraph(ResearchWorkflowState)

        async def plan(state: ResearchWorkflowState) -> ResearchWorkflowState:
            task = await self.repository.require(context.tenant_id, state["task_id"])
            questions = normalize_questions(await planner(str(task["userInput"])), str(task["userInput"]))
            step = await self.repository.start_step(
                context.tenant_id,
                state["task_id"],
                "ResearchPlanner",
                1,
                {"topic": task["userInput"]},
            )
            await self.repository.complete_step(
                context.tenant_id,
                state["task_id"],
                str(step["stepId"]),
                thought="Decomposed the topic into tenant-scoped research questions.",
                action="plan_research",
                action_input={"topic": task["userInput"]},
                observation={"subQuestions": questions},
                next_status="SEARCHING",
                phase="retrieving",
                state_patch={"subquestions": questions, "retrievals": {}},
                extra_events=[("PLANNED", {"subQuestionCount": len(questions)})],
            )
            return {"phase": "retrieving"}

        async def retrieve(state: ResearchWorkflowState) -> ResearchWorkflowState:
            task_id = state["task_id"]
            checkpoint = await self.repository.state(context.tenant_id, task_id) or {}
            questions = normalize_questions(checkpoint.get("subquestions"), "")
            if not questions:
                raise ResearchNotResumable("research plan checkpoint is missing")
            stored = checkpoint.get("retrievals")
            retrievals = dict(stored) if isinstance(stored, Mapping) else {}
            missing = [question for question in questions if question not in retrievals]
            steps = [
                await self.repository.start_step(
                    context.tenant_id,
                    task_id,
                    "RagResearchAgent",
                    index + 2,
                    {"subQuestion": question},
                )
                for index, question in enumerate(questions)
                if question in missing
            ]
            results = await asyncio.gather(
                *(retriever(question, task_id) for question in missing)
            )
            by_question = dict(zip(missing, results, strict=True))
            for question, step in zip(missing, steps, strict=True):
                result = normalize_retrieval(by_question[question])
                retrievals[question] = result
                await self.repository.complete_step(
                    context.tenant_id,
                    task_id,
                    str(step["stepId"]),
                    thought="Retrieved and ranked tenant-scoped evidence.",
                    action="hybrid_retrieval",
                    action_input={"subQuestion": question},
                    observation={"evidenceCount": len(result["evidence"])},
                    phase="retrieving",
                    state_patch={"retrievals": retrievals},
                )
            findings = findings_from(retrievals, questions)
            judge = await self.repository.start_step(
                context.tenant_id,
                task_id,
                "EvidenceJudge",
                len(questions) + 2,
                {"topic": checkpoint.get("userInput")},
            )
            evidence_count = sum(len(item["evidence"]) for item in findings)
            await self.repository.complete_step(
                context.tenant_id,
                task_id,
                str(judge["stepId"]),
                thought="Accepted only evidence returned by tenant-scoped retrieval.",
                action="judge_evidence",
                action_input={"subQuestionCount": len(questions)},
                observation={"evidenceCount": evidence_count, "accepted": evidence_count},
                next_status="WRITING",
                phase="writing",
                state_patch={"findings": findings},
                extra_events=[("EVIDENCE_JUDGED", {"evidenceCount": evidence_count})],
            )
            return {"phase": "writing"}

        async def write(state: ResearchWorkflowState) -> ResearchWorkflowState:
            task_id = state["task_id"]
            task = await self.repository.require(context.tenant_id, task_id)
            checkpoint = await self.repository.state(context.tenant_id, task_id) or {}
            raw_findings = checkpoint.get("findings")
            findings = [dict(item) for item in raw_findings] if isinstance(raw_findings, list) else []
            report = (await writer(str(task["userInput"]), findings)).strip()
            if not report:
                raise ValueError("research writer returned an empty report")
            step = await self.repository.start_step(
                context.tenant_id,
                task_id,
                "ReportWriter",
                len(findings) + 3,
                {"topic": task["userInput"]},
            )
            await self.repository.complete_step(
                context.tenant_id,
                task_id,
                str(step["stepId"]),
                thought="Wrote a Markdown report from accepted evidence only.",
                action="write_report",
                action_input={"topic": task["userInput"]},
                observation={"reportLength": len(report)},
                phase="reported",
                state_patch={"report": report},
                extra_events=[("REPORT_WRITTEN", {"reportLength": len(report)})],
            )
            return {"phase": "reported", "report": report}

        async def finish(state: ResearchWorkflowState) -> ResearchWorkflowState:
            report = state.get("report")
            if not isinstance(report, str):
                raise ResearchNotResumable("research report checkpoint is missing")
            await self.repository.complete_task(context.tenant_id, state["task_id"], report, {"report": report})
            return {"phase": "done", "report": report}

        def route(state: ResearchWorkflowState) -> str:
            routes = {
                "planning": "plan",
                "retrieving": "retrieve",
                "writing": "write",
                "reported": "finish",
            }
            try:
                return routes[str(state.get("phase"))]
            except KeyError as exc:
                raise ResearchNotResumable("research checkpoint phase is invalid") from exc

        graph.add_node("plan", plan)
        graph.add_node("retrieve", retrieve)
        graph.add_node("write", write)
        graph.add_node("finish", finish)
        graph.add_conditional_edges(
            START,
            route,
            {"plan": "plan", "retrieve": "retrieve", "write": "write", "finish": "finish"},
        )
        graph.add_edge("plan", "retrieve")
        graph.add_edge("retrieve", "write")
        graph.add_edge("write", "finish")
        graph.add_edge("finish", END)
        return graph.compile()


def normalize_questions(value: Any, fallback: str) -> list[str]:
    raw = value if isinstance(value, list) else []
    questions: list[str] = []
    for item in raw:
        question = str(item).strip()
        if question and question not in questions:
            questions.append(question[:500])
    return questions[:4] or ([fallback] if fallback else [])


def normalize_retrieval(value: Mapping[str, Any]) -> dict[str, Any]:
    evidence = [str(item) for item in value.get("evidence", []) if str(item).strip()][:5]
    citations = [dict(item) for item in value.get("citations", []) if isinstance(item, Mapping)][:5]
    stats = dict(value.get("retrievalStats") or {}) if isinstance(value.get("retrievalStats"), Mapping) else {}
    return {"evidence": evidence, "citations": citations, "retrievalStats": stats}


def findings_from(retrievals: Mapping[str, Any], questions: list[str]) -> list[dict[str, Any]]:
    return [
        {"question": question, **normalize_retrieval(value)}
        for question in questions
        if isinstance((value := retrievals.get(question)), Mapping)
    ]


def parse_research_questions(answer: str, topic: str) -> list[str]:
    questions: list[str] = []
    for line in answer.splitlines():
        question = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if question and question not in questions:
            questions.append(question[:500])
    return questions[:4] or [topic]


def research_evidence_text(findings: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for index, finding in enumerate(findings, start=1):
        evidence = [str(item) for item in finding.get("evidence", []) if str(item).strip()]
        if evidence:
            sections.append(f"[{index}] {finding.get('question', '')}: {evidence[0][:800]}")
    return "\n".join(sections)


def fallback_research_report(topic: str, findings: list[dict[str, Any]]) -> str:
    sections = [f"# {topic}", "", "## Findings"]
    for index, finding in enumerate(findings, start=1):
        evidence = [str(item) for item in finding.get("evidence", []) if str(item).strip()]
        if evidence:
            sections.extend([f"### {finding.get('question', topic)}", evidence[0][:800], f"[{index}]"])
    return "\n\n".join(sections) + "\n"
