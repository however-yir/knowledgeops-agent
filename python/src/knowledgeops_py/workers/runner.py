from __future__ import annotations

import argparse
import asyncio
import signal
from pathlib import Path

from knowledgeops_py.app import create_app, process_pending_jobs
from knowledgeops_py.application.ingestion import IngestionApplicationService
from knowledgeops_py.config import load_settings
from knowledgeops_py.infrastructure.database import create_engine, create_session_factory
from knowledgeops_py.infrastructure.file_store import LocalFileStore
from knowledgeops_py.infrastructure.ingestion_repository import SqlAlchemyIngestionRepository
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
        service = IngestionApplicationService(
            SqlAlchemyIngestionRepository(create_session_factory(engine)),
            LocalFileStore(Path(settings.storage_path)),
            settings.ingestion_queue_backend,
            queue,
        )
        try:
            if queue is not None:
                async for job_id in queue.consume():
                    await service.process_message(job_id)
                    if once or stopping.is_set():
                        return
            while not stopping.is_set():
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
