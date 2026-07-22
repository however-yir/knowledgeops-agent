from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from redis.exceptions import RedisError

from knowledgeops_py.application.ingestion import IngestionApplicationService
from knowledgeops_py.domain.context import TenantContext
from knowledgeops_py.domain.ports import (
    ChatProvider,
    EmbeddingProvider,
    IngestionQueue,
    Reranker,
    ToolRuntime,
    VectorStore,
)
from knowledgeops_py.infrastructure.database import create_engine, create_session_factory, session_scope
from knowledgeops_py.infrastructure.file_store import LocalFileStore
from knowledgeops_py.infrastructure.ingestion_repository import SqlAlchemyIngestionRepository
from knowledgeops_py.infrastructure.memory_repository import SqlAlchemyMemoryRepository
from knowledgeops_py.infrastructure.models import (
    ApiKeyRecord,
    AuditLogRecord,
    Base,
    EvaluationRunRecord,
    GraphEntityRecord,
    IngestionJobRecord,
    MemoryRecord,
    RefreshTokenRecord,
    SessionRecord,
    TenantBudgetRecord,
    WorkflowEventRecord,
    WorkflowStepRecord,
    WorkflowTaskRecord,
)
from knowledgeops_py.infrastructure.oidc_state import OidcStateUnavailable, RedisOidcStateStore
from knowledgeops_py.infrastructure.providers import (
    OpenAICompatibleChatProvider,
    OpenAICompatibleEmbeddingProvider,
    RemoteHttpReranker,
)
from knowledgeops_py.infrastructure.queues import MySqlPollingIngestionQueue, RedisStreamsIngestionQueue
from knowledgeops_py.infrastructure.security_repository import SqlAlchemySecurityRepository, StoredIdentity
from knowledgeops_py.infrastructure.session_repository import SqlAlchemySessionRepository
from knowledgeops_py.infrastructure.workflow_repository import SqlAlchemyWorkflowRepository
from knowledgeops_py.scripts.java_baseline_manifest import build_manifest


def test_domain_ports_and_tenant_context_are_framework_independent() -> None:
    context = TenantContext("trace", "tenant", "principal", ("ADMIN",), ("PERM_CHAT_WRITE",), "jwt")
    assert context.has("PERM_CHAT_WRITE")
    for port in (ChatProvider, EmbeddingProvider, Reranker, VectorStore, IngestionQueue, ToolRuntime):
        assert port.__module__ == "knowledgeops_py.domain.ports"


def test_async_database_metadata_and_transaction_scope() -> None:
    async def exercise() -> None:
        engine = create_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = create_session_factory(engine)
        async for session in session_scope(factory):
            session.add(
                ApiKeyRecord(
                    key_hash="hash",
                    key_name="key",
                    role="ADMIN",
                    tenant_id="tenant",
                    enabled=True,
                )
            )
        await engine.dispose()

    asyncio.run(exercise())
    assert {
        ApiKeyRecord,
        RefreshTokenRecord,
        IngestionJobRecord,
        SessionRecord,
        AuditLogRecord,
        TenantBudgetRecord,
        MemoryRecord,
        GraphEntityRecord,
        WorkflowTaskRecord,
        WorkflowStepRecord,
        WorkflowEventRecord,
        EvaluationRunRecord,
    }


def test_fixed_java_baseline_manifest_is_generated_from_the_requested_sha() -> None:
    repository = Path(__file__).resolve().parents[2]
    manifest = build_manifest(repository, "ac62bb3a83239b1b3a8701fcdcad7d337c2c400a")
    assert manifest["baselineSha"] == "ac62bb3a83239b1b3a8701fcdcad7d337c2c400a"
    assert "src/main/resources/db/migration/V14__agent_harness_permissions.sql" in manifest["migrations"]
    assert {"trace", "token", "done", "error"} == set(manifest["sseEventContract"])
    assert any(route["path"] == "/auth/token" for route in manifest["routes"])


def test_openai_compatible_and_remote_reranker_adapters(monkeypatch) -> None:
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self.payload

    class Client:
        def __init__(self, *args, **kwargs):
            self.base_url = kwargs.get("base_url")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, path, **kwargs):
            if path == "/chat/completions":
                return Response({"model": "test", "choices": [{"message": {"content": "answer"}}], "usage": {"prompt_tokens": 2}})
            if path == "/embeddings":
                return Response({"data": [{"embedding": [0.1, 0.2]}]})
            return Response({"scores": [0.9]})

    monkeypatch.setattr("knowledgeops_py.infrastructure.providers.httpx.AsyncClient", Client)
    context = TenantContext("trace", "tenant", "principal", (), (), "test")

    async def exercise() -> None:
        chat = await OpenAICompatibleChatProvider("https://model", "key", "model").complete(context, "prompt", "quality")
        embeddings = await OpenAICompatibleEmbeddingProvider("https://model", "key", "embedding").embed(context, ["prompt"])
        scores = await RemoteHttpReranker("https://reranker").rank(context, "q", ["d"])
        assert chat["answer"] == "answer"
        assert embeddings == [[0.1, 0.2]]
        assert scores == [0.9]

    asyncio.run(exercise())


def test_redis_streams_and_mysql_skip_locked_queue_adapters() -> None:
    class RedisClient:
        def __init__(self) -> None:
            self.added = []

        async def xadd(self, stream, fields) -> None:
            self.added.append((stream, fields))

        async def xgroup_create(self, *args, **kwargs) -> None:
            return None

        async def xreadgroup(self, *args, **kwargs):
            return [("stream", [("message-1", {"jobId": "redis-job"})])]

        async def xack(self, *args) -> None:
            return None

    async def exercise() -> None:
        client = RedisClient()
        queue = RedisStreamsIngestionQueue(client)  # type: ignore[arg-type]
        context = TenantContext("trace", "tenant", "principal", (), (), "test")
        await queue.publish(context, "redis-job")
        assert client.added[0][1]["tenantId"] == "tenant"
        consumer = queue.consume()
        assert await anext(consumer) == "redis-job"
        await consumer.aclose()

        engine = create_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = create_session_factory(engine)
        async for session in session_scope(factory):
            session.add(
                IngestionJobRecord(
                    job_id="sql-job",
                    tenant_id="tenant",
                    chat_id="chat",
                    source_name="source",
                    status="QUEUED",
                    idempotency_key="idem",
                    payload={},
                )
            )
        assert await MySqlPollingIngestionQueue(factory).claim() == "sql-job"
        await engine.dispose()

    asyncio.run(exercise())


def test_sql_security_repository_persists_rotation_and_single_use_refresh_tokens() -> None:
    async def exercise() -> None:
        engine = create_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = create_session_factory(engine)
        first = SqlAlchemySecurityRepository(factory)
        await first.bootstrap_api_key("demo-secret", "demo", "tenant-a", "ADMIN")
        assert (await first.authenticate_api_key("demo-secret")) == StoredIdentity("demo", "tenant-a", ("ADMIN",), "api_key")

        issued = await first.issue_api_key("reporter", "USER", "tenant-a", 30)
        second = SqlAlchemySecurityRepository(factory)
        assert (await second.authenticate_api_key(issued.raw_key)).tenant_id == "tenant-a"  # type: ignore[union-attr]
        rotated = await second.rotate_api_key("reporter", "tenant-a", "rotation", 30)
        assert rotated is not None
        assert await first.authenticate_api_key(issued.raw_key) is None
        assert (await first.authenticate_api_key(rotated.raw_key)).roles == ("USER",)  # type: ignore[union-attr]

        refresh = await first.issue_refresh_token(StoredIdentity("alice", "tenant-a", ("USER",), "jwt"), 7)
        consumed = await second.consume_refresh_token(refresh)
        assert consumed == StoredIdentity("alice", "tenant-a", ("USER",), "refresh_token")
        assert await first.consume_refresh_token(refresh) is None
        await engine.dispose()

    asyncio.run(exercise())


def test_redis_oidc_state_store_consumes_once_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        values: dict[str, str] = {}
        fail = False

        async def set(self, key: str, value: str, ex: int) -> None:
            assert ex == 60
            self.values[key] = value

        async def getdel(self, key: str) -> str | None:
            if self.fail:
                raise RedisError("unavailable")
            return self.values.pop(key, None)

        async def aclose(self) -> None:
            return None

    client = Client()
    monkeypatch.setattr("knowledgeops_py.infrastructure.oidc_state.redis.Redis.from_url", lambda *args, **kwargs: client)

    async def exercise() -> None:
        store = RedisOidcStateStore("redis://example.test")
        await store.put("exchange", "hashed", {"principal": "alice"}, 60)
        assert await store.consume("exchange", "hashed") == {"principal": "alice"}
        assert await store.consume("exchange", "hashed") is None
        client.fail = True
        with pytest.raises(OidcStateUnavailable):
            await store.consume("exchange", "hashed")

    asyncio.run(exercise())


def test_sql_session_repository_persists_messages_flags_and_tenant_boundary() -> None:
    async def exercise() -> None:
        engine = create_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        repository = SqlAlchemySessionRepository(create_session_factory(engine))

        assert await repository.list("tenant-a") == []
        assert await repository.get("tenant-a", "missing") is None
        created = await repository.upsert(
            "tenant-a",
            "session-1",
            {"title": "Initial", "chatId": "chat-1", "workspace": "team", "pinned": True},
        )
        assert created is not None and created["workspace"] == "team" and created["pinned"] is True
        appended = await repository.append_turn("tenant-a", "session-1", "chat-1", "question", "answer", "quality")
        assert appended is not None and [message["content"] for message in appended["messages"]] == ["question", "answer"]
        updated = await repository.upsert(
            "tenant-a",
            "session-1",
            {"title": "Updated", "branches": [{"id": "main"}], "archived": True, "streaming": False},
        )
        assert updated is not None and updated["title"] == "Updated" and updated["archived"] is True
        assert updated["branches"] == [{"id": "main"}] and updated["streaming"] is False
        unarchived = await repository.set_flag("tenant-a", "session-1", "archived", False)
        assert unarchived is not None and unarchived["archived"] is False
        assert len(await repository.list("tenant-a")) == 1
        assert await repository.get("tenant-b", "session-1") is None
        assert await repository.upsert("tenant-b", "session-1", {}) is None
        assert await repository.set_flag("tenant-a", "missing", "pinned", True) is None
        with pytest.raises(ValueError, match="unsupported session flag"):
            await repository.set_flag("tenant-a", "session-1", "invalid", True)
        new_turn = await repository.append_turn("tenant-a", "session-2", "chat-2", "next", "saved", "balanced")
        assert new_turn is not None and new_turn["messages"][1]["content"] == "saved"
        await engine.dispose()

    asyncio.run(exercise())


def test_sql_workflow_repository_persists_tasks_steps_events_and_tenant_boundary() -> None:
    async def exercise() -> None:
        engine = create_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        repository = SqlAlchemyWorkflowRepository(create_session_factory(engine))
        task = await repository.create_completed(
            "tenant-a",
            "REACT",
            "find evidence",
            "quality",
            "chat-a",
            "grounded answer",
            [{"thoughtSummary": "retrieve", "action": "hybrid_retrieval", "actionInput": {"q": "evidence"}, "observation": {"hits": 1}}],
            [{"type": "EVIDENCE_JUDGED", "payload": {"accepted": 1}}],
        )
        assert task["status"] == "DONE" and task["steps"][0]["action"] == "hybrid_retrieval"
        assert {event["type"] for event in task["events"]} >= {"TASK_CREATED", "STEP_COMPLETED", "EVIDENCE_JUDGED", "TASK_COMPLETED"}
        assert (await repository.get("tenant-a", task["taskId"]))["finalOutput"] == "grounded answer"  # type: ignore[index]
        assert len(await repository.list_tasks("tenant-a", 10)) == 1
        assert await repository.get("tenant-b", task["taskId"]) is None
        assert await repository.events("tenant-b", task["taskId"]) is None
        simple = await repository.create_completed("tenant-a", "RESEARCH", "topic", "quality", "", "report", [], None)
        assert [event["type"] for event in simple["events"]] == ["TASK_CREATED", "TASK_COMPLETED"]
        await engine.dispose()

    asyncio.run(exercise())


def test_sql_memory_repository_scopes_items_by_tenant_principal_and_session() -> None:
    async def exercise() -> None:
        engine = create_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        repository = SqlAlchemyMemoryRepository(create_session_factory(engine))
        first = await repository.create("tenant-a", "alice", "Use concise answers.", "fact", "session-1")
        await repository.create("tenant-a", "alice", "A separate session.", "short", "session-2")
        await repository.create("tenant-a", "bob", "Other principal.", "fact", "session-1")
        await repository.create("tenant-b", "alice", "Other tenant.", "fact", "session-1")
        assert (await repository.list("tenant-a", "alice", "session-1"))[0]["memoryId"] == first["memoryId"]
        assert {item["content"] for item in await repository.list("tenant-a", "alice")} == {"Use concise answers.", "A separate session."}
        assert await repository.list("tenant-b", "alice")
        await engine.dispose()

    asyncio.run(exercise())


def test_durable_ingestion_is_idempotent_recovers_chunks_and_retries_failures(tmp_path: Path) -> None:
    class RecordingQueue:
        def __init__(self) -> None:
            self.published: list[str] = []
            self.dead_letters: list[str] = []

        async def publish(self, context: TenantContext, job_id: str) -> None:
            assert context.tenant_id == "tenant-a"
            self.published.append(job_id)

        async def publish_dead_letter(self, context: TenantContext, job_id: str, reason: str) -> None:
            assert context.tenant_id == "tenant-a"
            assert reason
            self.dead_letters.append(job_id)

        def consume(self) -> AsyncIterator[str]:
            async def no_messages() -> AsyncIterator[str]:
                if False:
                    yield "unreachable"

            return no_messages()

    async def exercise() -> None:
        engine = create_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        repository = SqlAlchemyIngestionRepository(create_session_factory(engine))
        files = LocalFileStore(tmp_path / "uploads")
        queue = RecordingQueue()
        service = IngestionApplicationService(repository, files, "db_polling", queue, max_retries=2, retry_delay_seconds=1)
        context = TenantContext("trace", "tenant-a", "alice", ("USER",), ("PERM_INGESTION_WRITE",), "jwt")

        submitted = await service.submit(context, "chat-a", "policy.txt", b"Water, rest, and shade prevent heat injury.")
        duplicate = await service.submit(context, "chat-a", "policy.txt", b"Water, rest, and shade prevent heat injury.")
        assert duplicate.job_id == submitted.job_id
        completed = await service.process(submitted.job_id)
        assert completed is not None and completed.status == "COMPLETED"
        assert await service.process(submitted.job_id) is None
        chunks = await repository.chunks("tenant-a", "chat-a")
        assert chunks[0]["content"].startswith("Water")
        reloaded = await repository.get("tenant-a", submitted.job_id)
        assert reloaded is not None and reloaded.file_path == submitted.file_path
        assert (await repository.list_jobs("tenant-a", "chat-a", 10))[0].job_id == submitted.job_id

        abandoned = await service.submit(context, "chat-a", "broken.txt", b"\xff")
        assert await repository.claim(abandoned.job_id) is not None
        assert await repository.recover_abandoned(lease_seconds=0) == 1
        assert await service.publish_ready() == 1
        assert queue.published[-1] == abandoned.job_id
        failed = await service.process_message(abandoned.job_id)
        assert failed is not None and failed.status == "FAILED" and failed.attempt_count == 2
        assert queue.dead_letters == [abandoned.job_id]
        with pytest.raises(ValueError, match="escapes tenant storage root"):
            await files.read("tenant-a", "/etc/passwd")
        await engine.dispose()

    asyncio.run(exercise())
