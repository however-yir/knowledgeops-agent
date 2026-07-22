from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knowledgeops_py.infrastructure.models import WorkflowEventRecord, WorkflowStepRecord, WorkflowTaskRecord


@dataclass(slots=True)
class SqlAlchemyWorkflowRepository:
    sessions: async_sessionmaker[AsyncSession]

    async def create_completed(
        self,
        tenant_id: str,
        task_type: str,
        user_input: str,
        model_profile: str,
        chat_id: str,
        final_output: str,
        steps: list[dict[str, Any]],
        events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        task_id = f"task_{uuid4().hex[:16]}"
        task = WorkflowTaskRecord(
            task_id=task_id,
            tenant_id=tenant_id,
            chat_id=chat_id,
            status="DONE",
            state={
                "type": task_type,
                "userInput": user_input,
                "finalOutput": final_output,
                "modelProfile": model_profile,
                "sessionId": chat_id,
            },
            updated_at=now,
        )
        task_events = [
            {"type": "TASK_CREATED", "payload": {"type": task_type}},
            *(events or []),
            {"type": "TASK_COMPLETED", "payload": {"status": "DONE"}},
        ]
        async with self.sessions() as session:
            session.add(task)
            for index, step in enumerate(steps, start=1):
                step_id = f"step_{uuid4().hex[:16]}"
                session.add(
                    WorkflowStepRecord(
                        step_id=step_id,
                        task_id=task_id,
                        tenant_id=tenant_id,
                        agent_name=str(step.get("agentName") or step.get("action") or "planner"),
                        status="COMPLETED",
                        step_order=index,
                        thought=str(step.get("thoughtSummary") or ""),
                        action=str(step.get("action") or ""),
                        action_input=dict(step.get("actionInput") or {}),
                        observation=dict(step.get("observation") or {}),
                        model_profile=model_profile,
                        started_at=now,
                        ended_at=now,
                    )
                )
                session.add(
                    WorkflowEventRecord(
                        event_id=f"evt_{uuid4().hex[:16]}",
                        task_id=task_id,
                        tenant_id=tenant_id,
                        step_id=step_id,
                        event_type="STEP_COMPLETED",
                        payload={"stepOrder": index, "action": step.get("action")},
                    )
                )
            for event in task_events:
                session.add(
                    WorkflowEventRecord(
                        event_id=f"evt_{uuid4().hex[:16]}",
                        task_id=task_id,
                        tenant_id=tenant_id,
                        step_id=None,
                        event_type=str(event["type"]),
                        payload=dict(event.get("payload") or {}),
                    )
                )
            await session.commit()
        return await self.require(tenant_id, task_id)

    async def list_tasks(self, tenant_id: str, limit: int) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            records = (
                await session.scalars(
                    select(WorkflowTaskRecord)
                    .where(WorkflowTaskRecord.tenant_id == tenant_id)
                    .order_by(WorkflowTaskRecord.created_at.desc())
                    .limit(limit)
                )
            ).all()
            return [await to_task(session, record, include_events=False) for record in records]

    async def get(self, tenant_id: str, task_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(WorkflowTaskRecord).where(WorkflowTaskRecord.tenant_id == tenant_id, WorkflowTaskRecord.task_id == task_id)
            )
            return await to_task(session, record, include_events=True) if record is not None else None

    async def require(self, tenant_id: str, task_id: str) -> dict[str, Any]:
        task = await self.get(tenant_id, task_id)
        if task is None:
            raise RuntimeError("workflow task disappeared after insert")
        return task

    async def events(self, tenant_id: str, task_id: str) -> list[dict[str, Any]] | None:
        async with self.sessions() as session:
            task = await session.scalar(
                select(WorkflowTaskRecord).where(WorkflowTaskRecord.tenant_id == tenant_id, WorkflowTaskRecord.task_id == task_id)
            )
            if task is None:
                return None
            records = (
                await session.scalars(
                    select(WorkflowEventRecord)
                    .where(WorkflowEventRecord.tenant_id == tenant_id, WorkflowEventRecord.task_id == task_id)
                    .order_by(WorkflowEventRecord.created_at)
                )
            ).all()
            return [to_event(record) for record in records]


async def to_task(session: AsyncSession, record: WorkflowTaskRecord, include_events: bool) -> dict[str, Any]:
    step_records = (
        await session.scalars(
            select(WorkflowStepRecord)
            .where(WorkflowStepRecord.tenant_id == record.tenant_id, WorkflowStepRecord.task_id == record.task_id)
            .order_by(WorkflowStepRecord.step_order)
        )
    ).all()
    state = record.state or {}
    task = {
        "taskId": record.task_id,
        "tenantId": record.tenant_id,
        "type": str(state.get("type") or "REACT"),
        "status": record.status,
        "userInput": str(state.get("userInput") or ""),
        "finalOutput": state.get("finalOutput"),
        "modelProfile": str(state.get("modelProfile") or "balanced"),
        "chatId": record.chat_id,
        "sessionId": state.get("sessionId"),
        "createdAt": as_utc(record.created_at).isoformat(),
        "updatedAt": as_utc(record.updated_at).isoformat(),
        "steps": [to_step(item) for item in step_records],
        "events": [],
    }
    if include_events:
        event_records = (
            await session.scalars(
                select(WorkflowEventRecord)
                .where(WorkflowEventRecord.tenant_id == record.tenant_id, WorkflowEventRecord.task_id == record.task_id)
                .order_by(WorkflowEventRecord.created_at)
            )
        ).all()
        task["events"] = [to_event(item) for item in event_records]
    return task


def to_step(record: WorkflowStepRecord) -> dict[str, Any]:
    return {
        "stepId": record.step_id,
        "taskId": record.task_id,
        "agentName": record.agent_name,
        "status": record.status,
        "stepOrder": record.step_order,
        "thought": record.thought,
        "action": record.action,
        "actionInput": record.action_input,
        "observation": record.observation,
        "modelProfile": record.model_profile,
        "startedAt": as_utc(record.started_at).isoformat(),
        "endedAt": as_utc(record.ended_at).isoformat() if record.ended_at else None,
    }


def to_event(record: WorkflowEventRecord) -> dict[str, Any]:
    return {
        "eventId": record.event_id,
        "taskId": record.task_id,
        "stepId": record.step_id,
        "type": record.event_type,
        "payload": record.payload,
        "createdAt": as_utc(record.created_at).isoformat(),
    }


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
