from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import aio_pika
import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knowledgeops_py.domain.context import TenantContext
from knowledgeops_py.infrastructure.models import IngestionJobRecord


@dataclass(slots=True)
class RedisStreamsIngestionQueue:
    client: redis.Redis
    stream: str = "knowledgeops:ingestion"
    group: str = "knowledgeops-python-workers"
    consumer: str = "worker-1"
    dead_letter_stream: str = "knowledgeops:ingestion:dlq"

    async def publish(self, context: TenantContext, job_id: str) -> None:
        await self.client.xadd(self.stream, {"jobId": job_id, "tenantId": context.tenant_id})

    async def publish_dead_letter(self, context: TenantContext, job_id: str, reason: str) -> None:
        await self.client.xadd(
            self.dead_letter_stream,
            {"jobId": job_id, "tenantId": context.tenant_id, "reason": reason[:1024]},
        )

    async def consume(self) -> AsyncIterator[str]:
        try:
            await self.client.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        while True:
            messages = await self.client.xreadgroup(self.group, self.consumer, {self.stream: ">"}, count=1, block=1000)
            for _, entries in messages:
                for message_id, fields in entries:
                    job_id = str(fields["jobId"])
                    yield job_id
                    await self.client.xack(self.stream, self.group, message_id)


@dataclass(slots=True)
class RabbitMqIngestionQueue:
    url: str
    queue_name: str = "knowledgeops.ingestion"
    dead_letter_queue: str = "knowledgeops.ingestion.dlq"

    async def publish(self, context: TenantContext, job_id: str) -> None:
        connection = await aio_pika.connect_robust(self.url)
        try:
            channel = await connection.channel(publisher_confirms=True)
            dead_letter = await channel.declare_queue(self.dead_letter_queue, durable=True)
            queue = await channel.declare_queue(
                self.queue_name,
                durable=True,
                arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": dead_letter.name},
            )
            body = json.dumps({"jobId": job_id, "tenantId": context.tenant_id}).encode()
            await channel.default_exchange.publish(aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT), queue.name)
        finally:
            await connection.close()

    async def publish_dead_letter(self, context: TenantContext, job_id: str, reason: str) -> None:
        connection = await aio_pika.connect_robust(self.url)
        try:
            channel = await connection.channel(publisher_confirms=True)
            queue = await channel.declare_queue(self.dead_letter_queue, durable=True)
            body = json.dumps({"jobId": job_id, "tenantId": context.tenant_id, "reason": reason[:1024]}).encode()
            await channel.default_exchange.publish(aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT), queue.name)
        finally:
            await connection.close()

    async def consume(self) -> AsyncIterator[str]:
        connection = await aio_pika.connect_robust(self.url)
        channel = await connection.channel()
        queue = await channel.declare_queue(self.queue_name, durable=True)
        try:
            async with queue.iterator() as iterator:
                async for message in iterator:
                    async with message.process(requeue=False):
                        payload = json.loads(message.body)
                        yield str(payload["jobId"])
        finally:
            await connection.close()


@dataclass(slots=True)
class MySqlPollingIngestionQueue:
    sessions: async_sessionmaker[AsyncSession]
    poll_interval_seconds: float = 1.0

    async def claim(self) -> str | None:
        async with self.sessions() as session:
            statement = (
                select(IngestionJobRecord)
                .where(IngestionJobRecord.status.in_(["QUEUED", "RETRY"]))
                .order_by(IngestionJobRecord.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            job = (await session.execute(statement)).scalar_one_or_none()
            if not job:
                return None
            job.status = "RUNNING"
            job.attempt_count += 1
            await session.commit()
            return job.job_id

    async def consume(self) -> AsyncIterator[str]:
        while True:
            job_id = await self.claim()
            if job_id:
                yield job_id
            else:
                await asyncio.sleep(self.poll_interval_seconds)
