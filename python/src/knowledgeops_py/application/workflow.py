"""Durable LangGraph orchestration for the Java-compatible workflow tables."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from knowledgeops_py.domain.context import TenantContext
from knowledgeops_py.infrastructure.workflow_repository import SqlAlchemyWorkflowRepository

WorkflowResponder = Callable[[], Awaitable[dict[str, Any]]]


class ReactWorkflowState(TypedDict, total=False):
    task_id: str
    phase: str
    response: dict[str, Any]


@dataclass(frozen=True, slots=True)
class WorkflowRunResult:
    task: dict[str, Any]
    response: dict[str, Any]


class WorkflowNotResumable(ValueError):
    """The task is terminal or was not created by the durable ReAct runner."""


@dataclass(slots=True)
class ReactWorkflowApplicationService:
    """Runs each LangGraph node through a durable repository checkpoint."""

    repository: SqlAlchemyWorkflowRepository

    async def run(
        self,
        context: TenantContext,
        user_input: str,
        model_profile: str,
        chat_id: str,
        responder: WorkflowResponder,
    ) -> WorkflowRunResult:
        task = await self.repository.start_task(
            context.tenant_id,
            "REACT",
            user_input,
            model_profile,
            chat_id,
            chat_id,
        )
        return await self._execute(context, task, responder)

    async def resume(
        self, context: TenantContext, task_id: str, responder: WorkflowResponder
    ) -> WorkflowRunResult:
        task = await self.repository.get(context.tenant_id, task_id)
        if task is None or task["type"] != "REACT" or task["status"] in {"DONE", "FAILED", "CANCELLED"}:
            raise WorkflowNotResumable("workflow task cannot be resumed")
        return await self._execute(context, task, responder)

    async def cancel(self, context: TenantContext, task_id: str) -> dict[str, Any] | None:
        task = await self.repository.get(context.tenant_id, task_id)
        if task is None or task["type"] != "REACT":
            return None
        if task["status"] in {"DONE", "FAILED", "CANCELLED"}:
            raise WorkflowNotResumable("workflow task is already terminal")
        return await self.repository.cancel_task(context.tenant_id, task_id)

    async def _execute(
        self, context: TenantContext, task: dict[str, Any], responder: WorkflowResponder
    ) -> WorkflowRunResult:
        state = await self.repository.state(context.tenant_id, str(task["taskId"])) or {}
        initial_state: ReactWorkflowState = {
            "task_id": str(task["taskId"]),
            "phase": str(state.get("phase") or "planning"),
        }
        stored_response = state.get("response")
        if isinstance(stored_response, dict):
            initial_state["response"] = stored_response
        try:
            result = await self._graph(context, responder).ainvoke(initial_state)
        except Exception as exc:
            await self.repository.fail_task(context.tenant_id, str(task["taskId"]), str(exc))
            raise
        completed = await self.repository.require(context.tenant_id, str(task["taskId"]))
        response = result.get("response")
        if not isinstance(response, dict):
            stored = (completed.get("state") or {}).get("response")
            if not isinstance(stored, dict):
                raise WorkflowNotResumable("workflow response checkpoint is missing")
            response = stored
        return WorkflowRunResult(completed, response)

    def _graph(self, context: TenantContext, responder: WorkflowResponder):
        graph = StateGraph(ReactWorkflowState)

        async def plan(state: ReactWorkflowState) -> ReactWorkflowState:
            task_id = state["task_id"]
            task = await self.repository.require(context.tenant_id, task_id)
            step = await self.repository.start_step(
                context.tenant_id,
                task_id,
                "planner",
                1,
                {"prompt": task["userInput"]},
            )
            await self.repository.complete_step(
                context.tenant_id,
                task_id,
                str(step["stepId"]),
                thought="Prepared a durable response plan.",
                action="plan",
                action_input={"prompt": task["userInput"]},
                observation={"next": "respond"},
                next_status="WRITING",
                phase="responding",
            )
            return {"phase": "responding"}

        async def respond(state: ReactWorkflowState) -> ReactWorkflowState:
            task_id = state["task_id"]
            task = await self.repository.require(context.tenant_id, task_id)
            step = await self.repository.start_step(
                context.tenant_id,
                task_id,
                "responder",
                2,
                {"prompt": task["userInput"]},
            )
            response = await responder()
            answer = str(response.get("answer") or "")
            await self.repository.complete_step(
                context.tenant_id,
                task_id,
                str(step["stepId"]),
                thought="Generated the workflow answer.",
                action="respond",
                action_input={"prompt": task["userInput"]},
                observation={"answerLength": len(answer)},
                phase="responded",
                state_patch={"response": response},
            )
            return {"phase": "responded", "response": response}

        async def finish(state: ReactWorkflowState) -> ReactWorkflowState:
            response = state.get("response")
            if not isinstance(response, dict):
                raise WorkflowNotResumable("workflow response checkpoint is missing")
            await self.repository.complete_task(
                context.tenant_id,
                state["task_id"],
                str(response.get("answer") or ""),
                {"response": response},
            )
            return {"phase": "done", "response": response}

        def route(state: ReactWorkflowState) -> str:
            if state.get("phase") == "planning":
                return "plan"
            if state.get("phase") == "responding":
                return "respond"
            if state.get("phase") == "responded":
                return "finish"
            raise WorkflowNotResumable("workflow checkpoint phase is invalid")

        graph.add_node("plan", plan)
        graph.add_node("respond", respond)
        graph.add_node("finish", finish)
        graph.add_conditional_edges(START, route, {"plan": "plan", "respond": "respond", "finish": "finish"})
        graph.add_edge("plan", "respond")
        graph.add_edge("respond", "finish")
        graph.add_edge("finish", END)
        return graph.compile()
