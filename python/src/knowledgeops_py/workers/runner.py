from __future__ import annotations

import argparse
import asyncio
import signal

from knowledgeops_py.app import create_app, process_pending_jobs
from knowledgeops_py.config import load_settings


async def run_worker(once: bool = False) -> None:
    settings = load_settings()
    app = create_app(settings)
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopping.set)
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
