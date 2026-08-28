"""Workflow hardening tests: step token persistence and abandoned-task recovery."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from knowledgeops_py.application.workflow import ReactWorkflowApplicationService
from knowledgeops_py.domain.context import TenantContext
from knowledgeops_py.infrastructure.database import create_engine, create_session_factory
from knowledgeops_py.infrastructure.models import Base
from knowledgeops_py.infrastructure.workflow_repository import SqlAlchemyWorkflowRepository


async def _repository() -> SqlAlchemyWorkflowRepository:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return SqlAlchemyWorkflowRepository(create_session_factory(engine))


def test_react_workflow_persists_step_token_usage() -> None:
    async def exercise() -> None:
        repository = await _repository()
        service = ReactWorkflowApplicationService(repository)
        context = TenantContext("trace", "tenant-a", "alice", ("ADMIN",), ("PERM_CHAT_WRITE",), "jwt")

        async def responder() -> dict[str, object]:
            return {
                "answer": "grounded answer",
                "usage": {"inputTokens": 120, "outputTokens": 30},
            }

        result = await service.run(context, "find evidence", "quality", "chat-tokens", responder)
        steps = {step["stepOrder"]: step for step in result.task["steps"]}
        assert steps[1]["inputTokens"] is None and steps[1]["outputTokens"] is None
        assert steps[2]["inputTokens"] == 120
        assert steps[2]["outputTokens"] == 30


def test_recover_abandoned_fails_only_stale_nonterminal_tasks() -> None:
    async def exercise() -> None:
        repository = await _repository()
        context = TenantContext("trace", "tenant-a", "alice", ("ADMIN",), ("PERM_CHAT_WRITE",), "jwt")

        fresh = await repository.start_task("tenant-a", "REACT", "fresh prompt", "balanced", "chat-fresh")
        stale = await repository.start_task("tenant-a", "REACT", "stale prompt", "balanced", "chat-stale")

        # Age the stale task beyond the grace period.
        async with repository.sessions() as session:
            from knowledgeops_py.infrastructure.models import WorkflowTaskRecord

            record = await session.get(WorkflowTaskRecord, stale["taskId"])
            assert record is not None
            record.updated_at = datetime.now(UTC) - timedelta(minutes=90)
            await session.commit()

        recovered = await repository.recover_abandoned(max_age_minutes=30)
        assert recovered == 1

        failed = await repository.get("tenant-a", stale["taskId"])
        still_running = await repository.get("tenant-a", fresh["taskId"])
        assert failed is not None and failed["status"] == "FAILED"
        assert still_running is not None and still_running["status"] == "PLANNING"
        assert any(event["type"] == "TASK_FAILED" for event in failed["events"])
        assert context is not None

    asyncio.run(exercise())
