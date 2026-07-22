from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knowledgeops_py.infrastructure.models import (
    EvaluationCaseRecord,
    EvaluationDatasetRecord,
    EvaluationResultRecord,
    EvaluationRunRecord,
)


@dataclass(slots=True)
class SqlAlchemyEvaluationRepository:
    sessions: async_sessionmaker[AsyncSession]

    async def ensure_default_dataset(self, tenant_id: str, name: str, cases: list[dict[str, Any]]) -> None:
        if await self.get_dataset(tenant_id, "default") is None:
            await self.create_dataset(tenant_id, "default", name, None, cases)

    async def create_dataset(
        self,
        tenant_id: str,
        dataset_id: str,
        name: str,
        description: str | None,
        cases: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = utc_now()
        dataset = EvaluationDatasetRecord(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            name=name,
            description=description,
            baseline_run_id=None,
            created_at=now,
            updated_at=now,
        )
        async with self.sessions() as session:
            session.add(dataset)
            for order, item in enumerate(cases):
                session.add(
                    EvaluationCaseRecord(
                        tenant_id=tenant_id,
                        dataset_id=dataset_id,
                        case_id=str(item.get("caseId") or f"case-{order + 1}"),
                        category=optional_text(item.get("category")),
                        chat_id=optional_text(item.get("chatId")),
                        question_text=str(item.get("question") or ""),
                        expected_citations=str_list(item.get("expectedCitations")),
                        expected_keywords=str_list(item.get("expectedKeywords")),
                        forbidden_keywords=str_list(item.get("forbiddenKeywords")),
                        sort_order=order,
                        created_at=now,
                        updated_at=now,
                    )
                )
            await session.commit()
        created = await self.get_dataset(tenant_id, dataset_id)
        if created is None:
            raise RuntimeError("evaluation dataset disappeared after insert")
        return created

    async def list_datasets(self, tenant_id: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            records = (
                await session.scalars(
                    select(EvaluationDatasetRecord)
                    .where(EvaluationDatasetRecord.tenant_id == tenant_id)
                    .order_by(EvaluationDatasetRecord.updated_at.desc())
                )
            ).all()
            return [await to_dataset(session, item) for item in records]

    async def get_dataset(self, tenant_id: str, dataset_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(EvaluationDatasetRecord).where(
                    EvaluationDatasetRecord.tenant_id == tenant_id,
                    EvaluationDatasetRecord.dataset_id == dataset_id,
                )
            )
            return await to_dataset(session, record) if record is not None else None

    async def create_completed_run(
        self,
        tenant_id: str,
        dataset_id: str,
        model_profile: str,
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = utc_now()
        run_id = f"run_{uuid4().hex[:16]}"
        metrics = summarize(results)
        async with self.sessions() as session:
            session.add(
                EvaluationRunRecord(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    dataset_id=dataset_id,
                    status="COMPLETED",
                    model_profile=model_profile,
                    total_cases=metrics["totalCases"],
                    passed_cases=metrics["passedCases"],
                    run_score=metrics["runScore"],
                    retrieval_hit_rate=metrics["retrievalHitRate"],
                    citation_coverage_rate=metrics["citationCoverageRate"],
                    answer_faithfulness_score=metrics["answerFaithfulnessScore"],
                    avg_latency_ms=metrics["avgLatencyMs"],
                    failure_rate=metrics["failureRate"],
                    error_message=None,
                    started_at=now,
                    finished_at=now,
                    created_at=now,
                    updated_at=now,
                    results={"resultIds": [str(item["resultId"]) for item in results]},
                )
            )
            for item in results:
                session.add(
                    EvaluationResultRecord(
                        tenant_id=tenant_id,
                        result_id=str(item["resultId"]),
                        run_id=run_id,
                        dataset_id=dataset_id,
                        case_id=str(item["caseId"]),
                        status=str(item["status"]),
                        question_text=str(item["question"]),
                        answer_text=optional_text(item.get("answer")),
                        citations=str_list(item.get("citations")),
                        evidence=str_list(item.get("evidence")),
                        retrieval_hit=float(item["retrievalHit"]),
                        citation_coverage=float(item["citationCoverage"]),
                        keyword_score=float(item["keywordScore"]),
                        answer_faithfulness=float(item["answerFaithfulness"]),
                        score=float(item["score"]),
                        latency_ms=int(item["latencyMs"]),
                        error_message=optional_text(item.get("errorMessage")),
                        created_at=now,
                    )
                )
            await session.commit()
        created = await self.get_run(tenant_id, run_id)
        if created is None:
            raise RuntimeError("evaluation run disappeared after insert")
        return created

    async def get_run(self, tenant_id: str, run_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(EvaluationRunRecord).where(
                    EvaluationRunRecord.tenant_id == tenant_id,
                    EvaluationRunRecord.run_id == run_id,
                )
            )
            return await to_run(session, record) if record is not None else None

    async def list_runs(self, tenant_id: str, dataset_id: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            records = (
                await session.scalars(
                    select(EvaluationRunRecord)
                    .where(
                        EvaluationRunRecord.tenant_id == tenant_id,
                        EvaluationRunRecord.dataset_id == dataset_id,
                    )
                    .order_by(EvaluationRunRecord.created_at.desc())
                )
            ).all()
            return [await to_run(session, item) for item in records]

    async def mark_baseline(self, tenant_id: str, run_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            run = await session.scalar(
                select(EvaluationRunRecord).where(
                    EvaluationRunRecord.tenant_id == tenant_id,
                    EvaluationRunRecord.run_id == run_id,
                )
            )
            if run is None:
                return None
            dataset = await session.scalar(
                select(EvaluationDatasetRecord).where(
                    EvaluationDatasetRecord.tenant_id == tenant_id,
                    EvaluationDatasetRecord.dataset_id == run.dataset_id,
                )
            )
            if dataset is None:
                return None
            dataset.baseline_run_id = run_id
            dataset.updated_at = utc_now()
            await session.commit()
        result = await self.get_run(tenant_id, run_id)
        if result is not None:
            result["isBaseline"] = True
        return result


async def to_dataset(session: AsyncSession, record: EvaluationDatasetRecord) -> dict[str, Any]:
    cases = (
        await session.scalars(
            select(EvaluationCaseRecord)
            .where(
                EvaluationCaseRecord.tenant_id == record.tenant_id,
                EvaluationCaseRecord.dataset_id == record.dataset_id,
            )
            .order_by(EvaluationCaseRecord.sort_order)
        )
    ).all()
    return {
        "datasetId": record.dataset_id,
        "tenantId": record.tenant_id,
        "name": record.name,
        "description": record.description,
        "baselineRunId": record.baseline_run_id,
        "caseCount": len(cases),
        "cases": [to_case(item) for item in cases],
        "createdAt": as_utc(record.created_at).isoformat(),
        "updatedAt": as_utc(record.updated_at).isoformat(),
    }


async def to_run(session: AsyncSession, record: EvaluationRunRecord) -> dict[str, Any]:
    records = (
        await session.scalars(
            select(EvaluationResultRecord)
            .where(EvaluationResultRecord.tenant_id == record.tenant_id, EvaluationResultRecord.run_id == record.run_id)
            .order_by(EvaluationResultRecord.id)
        )
    ).all()
    return {
        "runId": record.run_id,
        "tenantId": record.tenant_id,
        "datasetId": record.dataset_id,
        "status": record.status,
        "modelProfile": record.model_profile,
        "metrics": {
            "runScore": round4(record.run_score),
            "totalCases": record.total_cases,
            "passedCases": record.passed_cases,
            "retrievalHitRate": round4(record.retrieval_hit_rate),
            "citationCoverageRate": round4(record.citation_coverage_rate),
            "answerFaithfulnessScore": round4(record.answer_faithfulness_score),
            "avgLatencyMs": round4(record.avg_latency_ms),
            "failureRate": round4(record.failure_rate),
        },
        "results": [to_result(item) for item in records],
        "errorMessage": record.error_message,
        "startedAt": as_utc(record.started_at).isoformat() if record.started_at else "",
        "finishedAt": as_utc(record.finished_at).isoformat() if record.finished_at else "",
        "createdAt": as_utc(record.created_at).isoformat(),
    }


def to_case(record: EvaluationCaseRecord) -> dict[str, Any]:
    return {
        "caseId": record.case_id,
        "category": record.category,
        "chatId": record.chat_id,
        "question": record.question_text,
        "expectedCitations": record.expected_citations,
        "expectedKeywords": record.expected_keywords,
        "forbiddenKeywords": record.forbidden_keywords,
    }


def to_result(record: EvaluationResultRecord) -> dict[str, Any]:
    return {
        "resultId": record.result_id,
        "caseId": record.case_id,
        "status": record.status,
        "question": record.question_text,
        "answer": record.answer_text or "",
        "citations": record.citations,
        "evidence": record.evidence,
        "retrievalHit": round4(record.retrieval_hit),
        "citationCoverage": round4(record.citation_coverage),
        "keywordScore": round4(record.keyword_score),
        "answerFaithfulness": round4(record.answer_faithfulness),
        "score": round4(record.score),
        "latencyMs": record.latency_ms,
        "errorMessage": record.error_message,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, float | int]:
    count = len(results)
    return {
        "totalCases": count,
        "passedCases": sum(float(item["score"]) >= 0.7 for item in results),
        "runScore": average(results, "score"),
        "retrievalHitRate": average(results, "retrievalHit"),
        "citationCoverageRate": average(results, "citationCoverage"),
        "answerFaithfulnessScore": average(results, "answerFaithfulness"),
        "avgLatencyMs": average(results, "latencyMs"),
        "failureRate": round4(sum(str(item["status"]) != "SUCCESS" for item in results) / count) if count else 0.0,
    }


def average(results: list[dict[str, Any]], key: str) -> float:
    return round4(sum(float(item[key]) for item in results) / len(results)) if results else 0.0


def str_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def round4(value: float) -> float:
    return round(value, 4)


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
