"""Reliability hardening tests: pooled clients and bounded confirmation state."""

from __future__ import annotations

import asyncio
from typing import Any

from knowledgeops_py.api.harness_routes import sweep_expired_confirmations
from knowledgeops_py.domain.runtime import PlatformStore
from knowledgeops_py.infrastructure.pgvector_store import PgVectorProjection
from knowledgeops_py.infrastructure.rate_limit import shared_client, shared_token_bucket


def test_redis_client_is_shared_per_url() -> None:
    first = shared_client("redis://localhost:6379/0")
    second = shared_client("redis://localhost:6379/0")
    other = shared_client("redis://localhost:6379/1")
    assert first is second
    assert first is not other


def test_shared_token_bucket_is_cached_per_url_and_capacity() -> None:
    first = shared_token_bucket("redis://localhost:6379/0", 120)
    second = shared_token_bucket("redis://localhost:6379/0", 120)
    other = shared_token_bucket("redis://localhost:6379/1", 120)
    smaller = shared_token_bucket("redis://localhost:6379/0", 60)

    assert first is second
    assert first is not other
    assert first is not smaller


def test_sweep_expired_confirmations_drops_only_expired() -> None:
    store: PlatformStore = PlatformStore()
    store.action_confirmations = {
        "expired": {"tenantId": "t", "expiresAt": 10, "used": False},
        "live": {"tenantId": "t", "expiresAt": 10_000, "used": False},
    }

    sweep_expired_confirmations(store, epoch_seconds=lambda: 1_000)

    assert set(store.action_confirmations) == {"live"}


def test_pgvector_projection_reuses_one_pool() -> None:
    created: list[str] = []

    class FakeConnection:
        async def fetch(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            return [{"chunk_id": "c1"}]

    class FakePool:
        def acquire(self) -> Any:
            class Acquire:
                async def __aenter__(self) -> FakeConnection:
                    return FakeConnection()

                async def __aexit__(self, *args: Any) -> None:
                    return None

            return Acquire()

    async def fake_create_pool(url: str, **kwargs: Any) -> FakePool:
        created.append(url)
        return FakePool()

    import knowledgeops_py.infrastructure.pgvector_store as module

    original = module.asyncpg.create_pool
    module.asyncpg.create_pool = fake_create_pool  # type: ignore[assignment]
    try:
        from knowledgeops_py.domain.context import TenantContext

        projection = PgVectorProjection("postgresql://user:pass@db:5432/kb", dimensions=2)

        async def exercise() -> None:
            context = TenantContext("trace", "tenant-a", "user", (), (), "api_key")
            first = await projection.search(context, "chat-1", [0.1, 0.2], 5)
            second = await projection.search(context, "chat-1", [0.1, 0.2], 5)
            assert first[0]["chunk_id"] == "c1"
            assert second[0]["chunk_id"] == "c1"

        asyncio.run(exercise())
    finally:
        module.asyncpg.create_pool = original

    assert created == ["postgresql://user:pass@db:5432/kb"]
