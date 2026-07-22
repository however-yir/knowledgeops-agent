from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from typing import cast
from urllib.parse import quote

import aio_pika
import pytest
from docker.errors import DockerException  # type: ignore[import-untyped]
from testcontainers.rabbitmq import RabbitMqContainer  # type: ignore[import-untyped]

from knowledgeops_py.domain.context import TenantContext
from knowledgeops_py.infrastructure.queues import RabbitMqIngestionQueue


def test_rabbitmq_queue_persists_delivery_and_routes_decode_failures_to_dlq(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TESTCONTAINERS_RYUK_DISABLED", "true")
    try:
        with RabbitMqContainer() as container:

            async def verify() -> None:
                url = (
                    f"amqp://{container.username}:{container.password}@{container.get_container_host_ip()}:"
                    f"{container.get_exposed_port(container.port)}/{quote(container.vhost, safe='')}"
                )
                queue = RabbitMqIngestionQueue(url)
                context = TenantContext("trace", "tenant-a", "worker", (), (), "worker")
                await queue.publish(context, "job-rabbit")

                consumer = cast(AsyncGenerator[str, None], queue.consume())
                assert await anext(consumer) == "job-rabbit"
                await consumer.aclose()

                connection = await aio_pika.connect_robust(queue.url)
                try:
                    channel = await connection.channel()
                    main = await queue.declare_queue(channel)
                    delivered = await main.get(fail=False)
                    assert delivered is not None
                    assert json.loads(delivered.body) == {"jobId": "job-rabbit", "tenantId": "tenant-a"}
                    await delivered.ack()
                    await channel.default_exchange.publish(aio_pika.Message(body=b"not-json"), main.name)
                finally:
                    await connection.close()

                consumer = cast(AsyncGenerator[str, None], queue.consume())
                with pytest.raises(json.JSONDecodeError):
                    await anext(consumer)
                await consumer.aclose()

                connection = await aio_pika.connect_robust(queue.url)
                try:
                    channel = await connection.channel()
                    dead_letter = await channel.declare_queue(queue.dead_letter_queue, durable=True)
                    routed = await dead_letter.get(fail=False)
                    assert routed is not None and routed.body == b"not-json"
                    await routed.ack()
                finally:
                    await connection.close()

            asyncio.run(verify())
    except DockerException as exc:
        detail = str(exc)
        if not os.getenv("CI") and ("registry-1.docker.io" in detail or "No such image: rabbitmq:" in detail):
            pytest.skip("Docker Hub is unavailable for the local RabbitMQ Testcontainer")
        raise
