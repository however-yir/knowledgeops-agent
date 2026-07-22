from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from redis.exceptions import RedisError

from knowledgeops_py.app import retrieve_chunks_with_semantics
from knowledgeops_py.application.ingestion import IngestionApplicationService
from knowledgeops_py.application.workflow import ReactWorkflowApplicationService, WorkflowNotResumable
from knowledgeops_py.config import Settings
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
from knowledgeops_py.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository
from knowledgeops_py.infrastructure.file_store import LocalFileStore
from knowledgeops_py.infrastructure.graph_repository import SqlAlchemyGraphRepository
from knowledgeops_py.infrastructure.ingestion_repository import SqlAlchemyIngestionRepository
from knowledgeops_py.infrastructure.memory_repository import SqlAlchemyMemoryRepository
from knowledgeops_py.infrastructure.models import (
    ApiKeyRecord,
    AuditLogRecord,
    Base,
    EvaluationCaseRecord,
    EvaluationDatasetRecord,
    EvaluationResultRecord,
    EvaluationRunRecord,
    GraphEntityRecord,
    GraphFactRecord,
    GraphRelationRecord,
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
from knowledgeops_py.infrastructure.pgvector_store import PgVectorProjection, asyncpg_url, vector_literal
from knowledgeops_py.infrastructure.providers import (
    LocalCrossEncoderReranker,
    OllamaChatProvider,
    OllamaEmbeddingProvider,
    OpenAICompatibleChatProvider,
    OpenAICompatibleEmbeddingProvider,
    RemoteHttpReranker,
    create_chat_provider,
    create_embedding_provider,
    create_reranker,
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
        GraphRelationRecord,
        GraphFactRecord,
        WorkflowTaskRecord,
        WorkflowStepRecord,
        WorkflowEventRecord,
        EvaluationDatasetRecord,
        EvaluationCaseRecord,
        EvaluationRunRecord,
        EvaluationResultRecord,
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
            if path == "/api/chat":
                return Response({"model": "qwen3:1.7b", "message": {"content": "ollama answer"}, "prompt_eval_count": 3, "eval_count": 5})
            if path == "/api/embed":
                return Response({"embeddings": [[0.3, 0.4]]})
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
        ollama_chat = await OllamaChatProvider("http://ollama", "qwen3:1.7b").complete(context, "prompt", "quality")
        ollama_embeddings = await OllamaEmbeddingProvider("http://ollama", "nomic-embed-text").embed(context, ["prompt"])
        assert ollama_chat == {
            "answer": "ollama answer",
            "model": "qwen3:1.7b",
            "usage": {"prompt_tokens": 3, "completion_tokens": 5},
        }
        assert ollama_embeddings == [[0.3, 0.4]]

    asyncio.run(exercise())
    ollama_settings = Settings(model_backend="ollama", reranker_backend="local")
    assert isinstance(create_chat_provider(ollama_settings), OllamaChatProvider)
    assert isinstance(create_embedding_provider(ollama_settings), OllamaEmbeddingProvider)
    assert isinstance(create_reranker(ollama_settings), LocalCrossEncoderReranker)


def test_semantic_retrieval_merges_vectors_and_applies_reranker() -> None:
    class Embeddings:
        async def embed(self, context: TenantContext, texts: list[str]) -> list[list[float]]:
            assert context.tenant_id == "tenant-a" and texts == ["heat safety"]
            return [[1.0, 0.0]]

    class Reranker:
        async def rank(self, context: TenantContext, query: str, documents: list[str]) -> list[float]:
            assert query == "heat safety" and len(documents) == 2
            return [0.1, 0.9]

    chunks = [
        {"chunkId": "chunk-a", "sourceName": "policy", "title": "A", "content": "heat safety guidance", "embedding": [1.0, 0.0]},
        {"chunkId": "chunk-b", "sourceName": "policy", "title": "B", "content": "hydration protocol", "embedding": [0.9, 0.1]},
    ]

    result = asyncio.run(
        retrieve_chunks_with_semantics(
            chunks,
            "heat safety",
            TenantContext("trace", "tenant-a", "alice", (), (), "jwt"),
            Embeddings(),  # type: ignore[arg-type]
            Reranker(),  # type: ignore[arg-type]
            True,
        )
    )

    assert [citation.chunkId for citation in result["citations"]] == ["chunk-b", "chunk-a"]
    assert result["retrievalStats"]["vectorMatches"] == 2


def test_pgvector_retrieval_merges_only_the_authenticated_tenant_and_chat() -> None:
    class Embeddings:
        async def embed(self, context: TenantContext, texts: list[str]) -> list[list[float]]:
            assert context.tenant_id == "tenant-a" and texts == ["heat safety"]
            return [[1.0, 0.0]]

    class Vectors:
        async def upsert(self, chunks: list[dict[str, object]]) -> None:
            raise AssertionError(f"retrieval must not upsert: {chunks}")

        async def search(
            self, context: TenantContext, chat_id: str, embedding: list[float], limit: int
        ) -> list[dict[str, object]]:
            assert context.tenant_id == "tenant-a" and chat_id == "chat-a"
            assert embedding == [1.0, 0.0] and limit == 5
            return [
                {
                    "chunk_id": "vector-a",
                    "tenant_id": "tenant-a",
                    "chat_id": "chat-a",
                    "source_name": "policy.txt",
                    "chunk_index": 0,
                    "content": "Heat safety requires water and shade.",
                    "score": 0.92,
                },
                {
                    "chunk_id": "foreign",
                    "tenant_id": "tenant-b",
                    "chat_id": "chat-a",
                    "source_name": "other.txt",
                    "chunk_index": 0,
                    "content": "This result must not cross tenant scope.",
                    "score": 0.99,
                },
            ]

    result = asyncio.run(
        retrieve_chunks_with_semantics(
            [{"chunkId": "lexical", "sourceName": "notes", "title": "notes", "content": "unrelated"}],
            "heat safety",
            TenantContext("trace", "tenant-a", "alice", (), (), "jwt"),
            Embeddings(),  # type: ignore[arg-type]
            None,
            True,
            vector_store=Vectors(),  # type: ignore[arg-type]
            chat_id="chat-a",
        )
    )

    assert [citation.chunkId for citation in result["citations"]] == ["vector-a"]
    assert result["retrievalStats"]["vectorMatches"] == 1


def test_pgvector_projection_preserves_tenant_scope_and_vector_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    class Connection:
        def __init__(self) -> None:
            self.upsert_rows: list[tuple[object, ...]] = []
            self.search_args: tuple[object, ...] = ()
            self.closed = False

        async def executemany(self, query: str, rows: list[tuple[object, ...]]) -> None:
            assert "ON CONFLICT (chunk_id)" in query and "$7::vector" in query
            self.upsert_rows = rows

        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            assert "WHERE tenant_id = $1 AND chat_id = $2" in query
            self.search_args = args
            return [
                {
                    "chunk_id": "chunk-1",
                    "tenant_id": "tenant-a",
                    "chat_id": "chat-1",
                    "source_name": "source.txt",
                    "chunk_index": 0,
                    "content": "heat safety",
                    "score": 0.91,
                }
            ]

        async def close(self) -> None:
            self.closed = True

    connection = Connection()

    async def connect(url: str) -> Connection:
        assert url == "postgresql://postgres:secret@pgvector/knowledgeops"
        return connection

    monkeypatch.setattr("knowledgeops_py.infrastructure.pgvector_store.asyncpg.connect", connect)
    projection = PgVectorProjection("postgresql+asyncpg://postgres:secret@pgvector/knowledgeops", dimensions=2)
    context = TenantContext("trace", "tenant-a", "alice", (), (), "jwt")

    async def exercise() -> None:
        await projection.upsert(
            [
                {
                    "chunk_id": "chunk-1",
                    "tenant_id": "tenant-a",
                    "chat_id": "chat-1",
                    "source_name": "source.txt",
                    "chunk_index": 0,
                    "content": "heat safety",
                    "embedding": [1.0, 0.5],
                }
            ]
        )
        records = await projection.search(context, "chat-1", [0.5, 1.0], 3)
        assert records[0]["chunk_id"] == "chunk-1"

    asyncio.run(exercise())
    assert connection.upsert_rows[0][-1] == "[1.0,0.5]"
    assert connection.search_args == ("tenant-a", "chat-1", "[0.5,1.0]", 3)
    assert connection.closed
    assert asyncpg_url("postgresql+asyncpg://db") == "postgresql://db"
    assert vector_literal([1, 0.5]) == "[1.0,0.5]"
    assert vector_literal([1, 0.5], dimensions=2) == "[1.0,0.5]"
    with pytest.raises(ValueError, match="non-empty"):
        vector_literal([])
    with pytest.raises(ValueError, match="2 dimensions"):
        vector_literal([1], dimensions=2)


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


def test_langgraph_react_workflow_checkpoints_response_and_resumes_without_reinvoking_provider() -> None:
    async def exercise() -> None:
        engine = create_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        repository = SqlAlchemyWorkflowRepository(create_session_factory(engine))
        service = ReactWorkflowApplicationService(repository)
        context = TenantContext("trace-a", "tenant-a", "alice", ("ADMIN",), ("PERM_CHAT_WRITE",), "jwt")
        calls = 0

        async def responder() -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {"chatId": "chat-a", "answer": "grounded answer", "model": "stub", "trace": []}

        completed = await service.run(context, "find evidence", "quality", "chat-a", responder)
        assert completed.task["status"] == "DONE" and completed.response["answer"] == "grounded answer"
        assert calls == 1
        event_types = {event["type"] for event in completed.task["events"]}
        assert {"TASK_CREATED", "STATE_CHANGED", "STEP_STARTED", "STEP_COMPLETED", "STATE_CHECKPOINTED", "TASK_COMPLETED"} <= event_types

        recovering = await repository.start_task("tenant-a", "REACT", "resume", "quality", "chat-a")
        step = await repository.start_step("tenant-a", recovering["taskId"], "responder", 2, {"prompt": "resume"})
        stored_response = {"chatId": "chat-a", "answer": "already persisted", "model": "stub", "trace": []}
        await repository.complete_step(
            "tenant-a",
            recovering["taskId"],
            step["stepId"],
            thought="Generated the workflow answer.",
            action="respond",
            action_input={"prompt": "resume"},
            observation={"answerLength": 17},
            next_status="WRITING",
            phase="responded",
            state_patch={"response": stored_response},
        )

        async def should_not_run() -> dict[str, object]:
            raise AssertionError("the provider must not be reinvoked after a response checkpoint")

        resumed = await service.resume(context, recovering["taskId"], should_not_run)
        assert resumed.task["status"] == "DONE" and resumed.response == stored_response
        with pytest.raises(WorkflowNotResumable):
            await service.resume(context, recovering["taskId"], should_not_run)

        cancellable = await repository.start_task("tenant-a", "REACT", "cancel", "quality", "chat-a")
        cancelled = await service.cancel(context, cancellable["taskId"])
        assert cancelled is not None and cancelled["status"] == "CANCELLED"
        after_late_completion = await repository.complete_task(
            "tenant-a", cancellable["taskId"], "a late model response"
        )
        assert after_late_completion["status"] == "CANCELLED"
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


def test_sql_evaluation_repository_persists_cases_results_baselines_and_tenant_boundaries() -> None:
    async def exercise() -> None:
        engine = create_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        repository = SqlAlchemyEvaluationRepository(create_session_factory(engine))
        dataset = await repository.create_dataset(
            "tenant-a",
            "dataset-1",
            "Heat safety",
            "grounded checks",
            [
                {
                    "caseId": "case-1",
                    "category": "safety",
                    "chatId": "heat-chat",
                    "question": "What prevents heat injury?",
                    "expectedCitations": ["policy"],
                    "expectedKeywords": ["water"],
                    "forbiddenKeywords": ["invented"],
                }
            ],
        )
        assert dataset["caseCount"] == 1 and dataset["cases"][0]["chatId"] == "heat-chat"
        run = await repository.create_completed_run(
            "tenant-a",
            "dataset-1",
            "quality",
            [
                {
                    "resultId": "result-1",
                    "caseId": "case-1",
                    "status": "SUCCESS",
                    "question": "What prevents heat injury?",
                    "answer": "Water and shade.",
                    "citations": ["vector:policy:chunk-1"],
                    "evidence": ["Water prevents heat injury."],
                    "retrievalHit": 1.0,
                    "citationCoverage": 1.0,
                    "keywordScore": 1.0,
                    "answerFaithfulness": 1.0,
                    "score": 1.0,
                    "latencyMs": 12,
                    "errorMessage": None,
                }
            ],
        )
        assert run["metrics"]["runScore"] == 1.0 and run["results"][0]["resultId"] == "result-1"
        assert (await repository.get_run("tenant-b", run["runId"])) is None
        baseline = await repository.mark_baseline("tenant-a", run["runId"])
        assert baseline is not None and baseline["isBaseline"] is True
        current_dataset = await repository.get_dataset("tenant-a", "dataset-1")
        assert current_dataset is not None and current_dataset["baselineRunId"] == run["runId"]
        assert len(await repository.list_runs("tenant-a", "dataset-1")) == 1
        assert await repository.get_dataset("tenant-b", "dataset-1") is None
        await engine.dispose()

    asyncio.run(exercise())


def test_sql_graph_repository_persists_entities_relations_facts_and_tenant_boundaries() -> None:
    async def exercise() -> None:
        engine = create_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        repository = SqlAlchemyGraphRepository(create_session_factory(engine))
        course = await repository.create_entity(
            "tenant-a", "Heat safety course", "COURSE", ["heat", "safety"], "Prevention guidance"
        )
        topic = await repository.create_entity("tenant-a", "Heat safety", "TOPIC")
        relation = await repository.create_relation(
            "tenant-a", course["entityId"], topic["entityId"], "BELONGS_TO", weight=0.9
        )
        assert relation is not None and relation["relationType"] == "BELONGS_TO"
        fact = await repository.create_fact(
            "tenant-a", "Heat safety", "REQUIRES", "Water and shade", confidence=0.95, source="policy"
        )
        assert fact["object"] == "Water and shade"
        assert {item["entityId"] for item in await repository.list_entities("tenant-a", "safety")} == {
            course["entityId"],
            topic["entityId"],
        }
        neighbors = await repository.neighbors("tenant-a", course["entityId"])
        assert neighbors is not None and neighbors[0]["entity"]["entityId"] == topic["entityId"]
        assert (await repository.search_facts("tenant-a", "shade"))[0]["factId"] == fact["factId"]
        assert await repository.get_entity("tenant-b", course["entityId"]) is None
        assert await repository.neighbors("tenant-b", course["entityId"]) is None
        assert await repository.create_relation("tenant-b", course["entityId"], topic["entityId"], "RELATED_TO") is None
        assert await repository.search_facts("tenant-b", "shade") == []
        await engine.dispose()

    asyncio.run(exercise())


def test_durable_ingestion_is_idempotent_recovers_chunks_and_retries_failures(tmp_path: Path) -> None:
    class RecordingEmbeddingProvider:
        async def embed(self, context: TenantContext, texts: list[str]) -> list[list[float]]:
            assert context.tenant_id == "tenant-a" and context.auth_source == "worker"
            return [[float(index + 1), 0.5] for index, _ in enumerate(texts)]

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

    class RecordingVectorStore:
        def __init__(self) -> None:
            self.upserts: list[list[dict[str, object]]] = []

        async def upsert(self, chunks: list[dict[str, object]]) -> None:
            self.upserts.append(chunks)

        async def search(
            self, context: TenantContext, chat_id: str, embedding: list[float], limit: int
        ) -> list[dict[str, object]]:
            return []

    async def exercise() -> None:
        engine = create_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        repository = SqlAlchemyIngestionRepository(create_session_factory(engine))
        files = LocalFileStore(tmp_path / "uploads")
        queue = RecordingQueue()
        vectors = RecordingVectorStore()
        service = IngestionApplicationService(
            repository,
            files,
            "db_polling",
            queue,
            embedding_provider=RecordingEmbeddingProvider(),
            vector_store=vectors,  # type: ignore[arg-type]
            max_retries=2,
            retry_delay_seconds=1,
        )
        context = TenantContext("trace", "tenant-a", "alice", ("USER",), ("PERM_INGESTION_WRITE",), "jwt")

        submitted = await service.submit(context, "chat-a", "policy.txt", b"Water, rest, and shade prevent heat injury.")
        duplicate = await service.submit(context, "chat-a", "policy.txt", b"Water, rest, and shade prevent heat injury.")
        assert duplicate.job_id == submitted.job_id
        completed = await service.process(submitted.job_id)
        assert completed is not None and completed.status == "COMPLETED"
        assert await service.process(submitted.job_id) is None
        chunks = await repository.chunks("tenant-a", "chat-a")
        assert chunks[0]["content"].startswith("Water")
        assert chunks[0]["embedding"] == [1.0, 0.5]
        assert vectors.upserts[0][0]["chunk_id"] == f"chunk_{hashlib.sha256(f'{submitted.job_id}:0'.encode()).hexdigest()[:16]}"
        assert vectors.upserts[0][0]["embedding"] == [1.0, 0.5]
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
