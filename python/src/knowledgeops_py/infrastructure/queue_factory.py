from __future__ import annotations

from typing import cast

import redis.asyncio as redis

from knowledgeops_py.config import Settings
from knowledgeops_py.domain.ports import IngestionQueue
from knowledgeops_py.infrastructure.queues import RabbitMqIngestionQueue, RedisStreamsIngestionQueue


def create_ingestion_queue(settings: Settings, consumer: str) -> IngestionQueue | None:
    backend = settings.ingestion_queue_backend.lower()
    if backend == "redis_stream":
        return cast(IngestionQueue, RedisStreamsIngestionQueue(redis.Redis.from_url(settings.redis_url, decode_responses=True), consumer=consumer))
    if backend == "rabbitmq":
        if not settings.rabbitmq_url:
            raise ValueError("APP_RABBITMQ_URL is required for rabbitmq ingestion")
        return cast(IngestionQueue, RabbitMqIngestionQueue(settings.rabbitmq_url))
    if backend in {"db_polling", "memory"}:
        return None
    raise ValueError(f"unsupported ingestion queue backend: {settings.ingestion_queue_backend}")


async def close_ingestion_queue(queue: IngestionQueue | None) -> None:
    client = getattr(queue, "client", None)
    if client is not None:
        await client.aclose()
