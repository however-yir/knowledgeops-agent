from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "knowledgeops-agent-python"
    host: str = "0.0.0.0"
    port: int = 3001
    cors_allowed_origins: tuple[str, ...] = ("http://localhost:8088", "http://localhost:5173")
    demo_api_key: str = "local-demo-api-key"
    demo_tenant_id: str = "public"
    token_ttl_seconds: int = 3600
    jwt_secret: str = "local-python-jwt-secret"
    rate_limit_per_minute: int = 120
    ingestion_queue_backend: str = "simple"
    redis_url: str = "redis://localhost:6379/0"
    vector_backend: str = "simple"


def load_settings() -> Settings:
    return Settings(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "3001")),
        cors_allowed_origins=_csv(os.getenv("APP_CORS_ALLOWED_ORIGINS"))
        or ("http://localhost:8088", "http://localhost:5173"),
        demo_api_key=os.getenv("APP_DEMO_API_KEY", "local-demo-api-key"),
        demo_tenant_id=os.getenv("APP_DEMO_TENANT_ID", "public"),
        token_ttl_seconds=int(os.getenv("APP_TOKEN_TTL_SECONDS", "3600")),
        jwt_secret=os.getenv("APP_JWT_SECRET", "local-python-jwt-secret"),
        rate_limit_per_minute=int(os.getenv("APP_RATE_LIMIT_PER_MINUTE", "120")),
        ingestion_queue_backend=os.getenv("APP_INGESTION_QUEUE_BACKEND", "simple"),
        redis_url=os.getenv("APP_REDIS_URL", "redis://localhost:6379/0"),
        vector_backend=os.getenv("APP_VECTOR_BACKEND", "simple"),
    )


def _csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())
