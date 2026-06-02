from __future__ import annotations

import uvicorn

from .config import load_settings


def run() -> None:
    settings = load_settings()
    uvicorn.run(
        "knowledgeops_py.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    run()
