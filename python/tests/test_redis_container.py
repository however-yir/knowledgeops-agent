from __future__ import annotations

import asyncio
import os

import pytest
import redis.asyncio as redis
from docker.errors import DockerException
from testcontainers.redis import RedisContainer

from knowledgeops_py.domain.context import TenantContext
from knowledgeops_py.infrastructure.queues import RedisStreamsIngestionQueue


def test_redis_streams_reclaims_crashed_consumer_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TESTCONTAINERS_RYUK_DISABLED", "true")
    try:
        with RedisContainer("redis:7.4-alpine") as container:

            async def verify() -> None:
                client = redis.Redis(
                    host=container.get_container_host_ip(),
                    port=container.get_exposed_port(6379),
                    decode_responses=True,
                )
                context = TenantContext("trace", "tenant-a", "worker", (), (), "worker")
                crashed = RedisStreamsIngestionQueue(client, consumer="crashed", recovery_idle_ms=0)
                await crashed.publish(context, "job-redis-recovery")
                crashed_messages = crashed.consume()
                assert await anext(crashed_messages) == "job-redis-recovery"
                await crashed_messages.aclose()

                recovered = RedisStreamsIngestionQueue(client, consumer="recovered", recovery_idle_ms=0)
                recovered_messages = recovered.consume()
                assert await anext(recovered_messages) == "job-redis-recovery"
                await recovered_messages.aclose()
                await client.aclose()

            asyncio.run(verify())
    except DockerException as exc:
        detail = str(exc)
        if not os.getenv("CI") and ("registry-1.docker.io" in detail or "No such image: redis:" in detail):
            pytest.skip("Docker Hub is unavailable for the local Redis Testcontainer")
        raise
