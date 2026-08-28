from __future__ import annotations

import argparse
import asyncio
import signal
from contextlib import suppress
from pathlib import Path

from knowledgeops_py.app import create_app, process_pending_jobs
from knowledgeops_py.application.ingestion import IngestionApplicationService
from knowledgeops_py.config import load_settings
from knowledgeops_py.infrastructure.database import create_engine, create_session_factory
from knowledgeops_py.infrastructure.file_store import LocalFileStore
from knowledgeops_py.infrastructure.ingestion_repository import SqlAlchemyIngestionRepository
from knowledgeops_py.infrastructure.pgvector_store import PgVectorProjection
from knowledgeops_py.infrastructure.providers import create_embedding_provider
from knowledgeops_py.infrastructure.queue_factory import close_ingestion_queue, create_ingestion_queue


async def run_worker(once: bool = False) -> None:
    settings = load_settings()
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopping.set)
    if settings.database_url:
        engine = create_engine(settings.database_url)
        queue = create_ingestion_queue(settings, "worker")
        embedding_provider = create_embedding_provider(settings)
        vector_store = (
            PgVectorProjection(settings.pgvector_url, settings.pgvector_dimensions)
            if settings.vector_backend == "pgvector" and settings.pgvector_url
            else None
        )
        service = IngestionApplicationService(
            SqlAlchemyIngestionRepository(create_session_factory(engine)),
            LocalFileStore(Path(settings.storage_path)),
            settings.ingestion_queue_backend,
            queue,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
        )
        try:
            if queue is not None:
                await service.recover_abandoned()
                if once:
                    await service.process_ready()
                    return

                async def republish_retries() -> None:
                    await service.publish_ready(include_queued=True)
                    while not stopping.is_set():
                        await service.recover_abandoned()
                        await service.publish_ready()
                        try:
                            await asyncio.wait_for(stopping.wait(), timeout=1.0)
                        except TimeoutError:
                            pass

                async def consume_messages() -> None:
                    async for job_id in queue.consume():
                        tenant = await service.repository.tenant_of(job_id)
                        await service.process_message(job_id, tenant)
                        if stopping.is_set():
                            return

                retry_task = asyncio.create_task(republish_retries())
                consumer_task = asyncio.create_task(consume_messages())
                stop_task = asyncio.create_task(stopping.wait())
                try:
                    done, _ = await asyncio.wait(
                        {retry_task, consumer_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done - {stop_task}:
                        task.result()
                finally:
                    for task in (retry_task, consumer_task, stop_task):
                        task.cancel()
                    with suppress(asyncio.CancelledError):
                        await asyncio.gather(retry_task, consumer_task, stop_task)
                return
            while not stopping.is_set():
                await service.recover_abandoned()
                processed = await service.process_ready()
                if once:
                    return
                await asyncio.sleep(0.1 if processed else 1.0)
        finally:
            await close_ingestion_queue(queue)
            await engine.dispose()
        return

    app = create_app(settings)
    while not stopping.is_set():
        processed = process_pending_jobs(app.state.store, settings)
        if once:
            return
        await asyncio.sleep(0.1 if processed else 1.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run KnowledgeOps asynchronous workers")
    parser.add_argument("--once", action="store_true", help="drain currently visible jobs then stop")
    args = parser.parse_args()
    asyncio.run(run_worker(once=args.once))


if __name__ == "__main__":
    main()
