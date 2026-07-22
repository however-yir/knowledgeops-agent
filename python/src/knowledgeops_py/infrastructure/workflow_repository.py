from __future__ import annotations

from collections.abc import Mapping
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

    async def start_task(
        self,
        tenant_id: str,
        task_type: str,
        user_input: str,
        model_profile: str,
        chat_id: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a durable task before the workflow invokes an external provider."""
        now = utc_now()
        task_id = f"task_{uuid4().hex[:16]}"
        task = WorkflowTaskRecord(
            task_id=task_id,
            tenant_id=tenant_id,
            chat_id=chat_id,
            status="PLANNING",
            state={
                "type": task_type,
                "userInput": user_input,
                "finalOutput": None,
                "modelProfile": model_profile,
                "sessionId": session_id or chat_id,
                "phase": "planning",
            },
            updated_at=now,
        )
        async with self.sessions() as session:
            session.add(task)
            session.add(
                workflow_event(task_id, tenant_id, None, "TASK_CREATED", {"type": task_type})
            )
            session.add(
                workflow_event(
                    task_id,
                    tenant_id,
                    None,
                    "STATE_CHANGED",
                    {"from": "CREATED", "to": "PLANNING"},
                )
            )
            await session.commit()
        return await self.require(tenant_id, task_id)

    async def start_step(
        self,
        tenant_id: str,
        task_id: str,
        agent_name: str,
        step_order: int,
        action_input: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return the same unfinished step on recovery instead of duplicating it."""
        now = utc_now()
        async with self.sessions() as session:
            task = await task_for_tenant(session, tenant_id, task_id)
            existing = await session.scalar(
                select(WorkflowStepRecord).where(
                    WorkflowStepRecord.tenant_id == tenant_id,
                    WorkflowStepRecord.task_id == task_id,
                    WorkflowStepRecord.step_order == step_order,
                    WorkflowStepRecord.status == "RUNNING",
                )
            )
            if existing is not None:
                return to_step(existing)
            step = WorkflowStepRecord(
                step_id=f"step_{uuid4().hex[:16]}",
                task_id=task_id,
                tenant_id=tenant_id,
                agent_name=agent_name,
                status="RUNNING",
                step_order=step_order,
                thought=None,
                action=None,
                action_input=dict(action_input),
                observation={},
                model_profile=str((task.state or {}).get("modelProfile") or "balanced"),
                started_at=now,
                ended_at=None,
            )
            session.add(step)
            session.add(
                workflow_event(
                    task_id,
                    tenant_id,
                    step.step_id,
                    "STEP_STARTED",
                    {"agentName": agent_name, "stepOrder": step_order},
                )
            )
            await session.commit()
            return to_step(step)

    async def complete_step(
        self,
        tenant_id: str,
        task_id: str,
        step_id: str,
        *,
        thought: str | None,
        action: str,
        action_input: Mapping[str, Any],
        observation: Mapping[str, Any],
        next_status: str | None = None,
        phase: str | None = None,
        state_patch: Mapping[str, Any] | None = None,
        extra_events: list[tuple[str, Mapping[str, Any]]] | None = None,
    ) -> None:
        """Persist a step result and its task checkpoint atomically."""
        now = utc_now()
        async with self.sessions() as session:
            task = await task_for_tenant(session, tenant_id, task_id)
            if task.status in {"DONE", "FAILED", "CANCELLED"}:
                return
            step = await session.scalar(
                select(WorkflowStepRecord).where(
                    WorkflowStepRecord.tenant_id == tenant_id,
                    WorkflowStepRecord.task_id == task_id,
                    WorkflowStepRecord.step_id == step_id,
                )
            )
            if step is None:
                raise WorkflowTaskNotFound(task_id)
            step.status = "COMPLETED"
            step.thought = thought
            step.action = action
            step.action_input = dict(action_input)
            step.observation = dict(observation)
            step.ended_at = now
            session.add(
                workflow_event(
                    task_id,
                    tenant_id,
                    step_id,
                    "STEP_COMPLETED",
                    {"status": "COMPLETED", "action": action},
                )
            )
            for event_type, payload in extra_events or []:
                session.add(workflow_event(task_id, tenant_id, None, event_type, payload))
            if next_status is not None:
                previous_status = task.status
                task.status = next_status
                session.add(
                    workflow_event(
                        task_id,
                        tenant_id,
                        None,
                        "STATE_CHANGED",
                        {"from": previous_status, "to": next_status},
                    )
                )
            if phase is not None or state_patch is not None:
                state = dict(task.state or {})
                if phase is not None:
                    state["phase"] = phase
                if state_patch is not None:
                    state.update(state_patch)
                task.state = state
                session.add(
                    workflow_event(task_id, tenant_id, None, "STATE_CHECKPOINTED", {"phase": state.get("phase")})
                )
            task.updated_at = now
            await session.commit()

    async def complete_task(
        self,
        tenant_id: str,
        task_id: str,
        final_output: str,
        state_patch: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        async with self.sessions() as session:
            task = await task_for_tenant(session, tenant_id, task_id)
            if task.status in {"DONE", "FAILED", "CANCELLED"}:
                await session.commit()
                return await self.require(tenant_id, task_id)
            previous_status = task.status
            state = dict(task.state or {})
            state["finalOutput"] = final_output
            state["phase"] = "done"
            if state_patch is not None:
                state.update(state_patch)
            task.status = "DONE"
            task.state = state
            task.updated_at = now
            session.add(
                workflow_event(task_id, tenant_id, None, "STATE_CHANGED", {"from": previous_status, "to": "DONE"})
            )
            session.add(workflow_event(task_id, tenant_id, None, "TASK_COMPLETED", {"status": "DONE"}))
            await session.commit()
        return await self.require(tenant_id, task_id)

    async def fail_task(self, tenant_id: str, task_id: str, error: str) -> None:
        await self._finish_terminal(tenant_id, task_id, "FAILED", error, "TASK_FAILED")

    async def cancel_task(self, tenant_id: str, task_id: str) -> dict[str, Any]:
        await self._finish_terminal(tenant_id, task_id, "CANCELLED", None, "TASK_CANCELLED")
        return await self.require(tenant_id, task_id)

    async def _finish_terminal(
        self, tenant_id: str, task_id: str, status: str, final_output: str | None, event_type: str
    ) -> None:
        now = utc_now()
        async with self.sessions() as session:
            task = await task_for_tenant(session, tenant_id, task_id)
            if task.status in {"DONE", "FAILED", "CANCELLED"}:
                return
            previous_status = task.status
            state = dict(task.state or {})
            state["phase"] = status.lower()
            if final_output is not None:
                state["finalOutput"] = final_output
            task.status = status
            task.state = state
            task.updated_at = now
            session.add(
                workflow_event(task_id, tenant_id, None, "STATE_CHANGED", {"from": previous_status, "to": status})
            )
            payload = {"status": status} if final_output is None else {"error": final_output}
            session.add(workflow_event(task_id, tenant_id, None, event_type, payload))
            await session.commit()

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

    async def state(self, tenant_id: str, task_id: str) -> dict[str, Any] | None:
        """Read the private graph checkpoint without changing the public task projection."""
        async with self.sessions() as session:
            record = await session.scalar(
                select(WorkflowTaskRecord).where(WorkflowTaskRecord.tenant_id == tenant_id, WorkflowTaskRecord.task_id == task_id)
            )
            return dict(record.state or {}) if record is not None else None

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


class WorkflowTaskNotFound(LookupError):
    """Raised when a tenant cannot access a workflow task or step."""


async def task_for_tenant(session: AsyncSession, tenant_id: str, task_id: str) -> WorkflowTaskRecord:
    task = await session.scalar(
        select(WorkflowTaskRecord).where(
            WorkflowTaskRecord.tenant_id == tenant_id,
            WorkflowTaskRecord.task_id == task_id,
        )
    )
    if task is None:
        raise WorkflowTaskNotFound(task_id)
    return task


def workflow_event(
    task_id: str,
    tenant_id: str,
    step_id: str | None,
    event_type: str,
    payload: Mapping[str, Any],
) -> WorkflowEventRecord:
    return WorkflowEventRecord(
        event_id=f"evt_{uuid4().hex[:16]}",
        task_id=task_id,
        tenant_id=tenant_id,
        step_id=step_id,
        event_type=event_type,
        payload=dict(payload),
    )
