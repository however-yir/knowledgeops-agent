from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "knowledgeops-agent-python"
    host: str = "127.0.0.1"
    port: int = 3001
    cors_allowed_origins: tuple[str, ...] = ("http://localhost:8088", "http://localhost:5173")
    demo_api_key: str = "local-demo-api-key"
    demo_tenant_id: str = "public"
    token_ttl_seconds: int = 3600
    refresh_token_ttl_days: int = 14
    jwt_secret: str = "local-python-jwt-secret-change-me"
    rate_limit_per_minute: int = 120
    environment: str = "development"
    ingestion_queue_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"
    vector_backend: str = "simple"
    database_url: str | None = None
    pgvector_url: str | None = None
    rabbitmq_url: str | None = None
    storage_backend: str = "local"
    storage_path: str = field(default_factory=lambda: str(Path(tempfile.gettempdir()) / "knowledgeops-files"))
    max_upload_bytes: int = 10 * 1024 * 1024
    oidc_issuer_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str | None = None
    model_base_url: str | None = None
    model_api_key: str | None = None
    model_name: str = "qwen-plus"
    reranker_backend: str = "identity"
    reranker_url: str | None = None
    allow_workspace_write: bool = False
    allow_workspace_shell: bool = False

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    def validate_startup(self) -> None:
        """Reject the demo-only configuration before a production process starts."""
        if not self.is_production:
            return
        defaults = {"", "local-python-jwt-secret-change-me", "replace-me-with-real-secret"}
        if self.jwt_secret in defaults:
            raise ValueError("APP_JWT_SECRET must be explicitly configured in production")
        if self.demo_api_key == "local-demo-api-key":
            raise ValueError("APP_DEMO_API_KEY must not use the development default in production")
        if not self.database_url:
            raise ValueError("APP_DATABASE_URL is required in production")
        if not self.redis_url:
            raise ValueError("APP_REDIS_URL is required in production")
        if not self.model_base_url or not self.model_api_key:
            raise ValueError("APP_MODEL_BASE_URL and APP_MODEL_API_KEY are required in production")
        if self.reranker_backend == "identity":
            raise ValueError("APP_RERANKER_BACKEND cannot be identity in production")
        if self.reranker_backend == "remote" and not self.reranker_url:
            raise ValueError("APP_RERANKER_URL is required for the remote production reranker")


def load_settings() -> Settings:
    settings = Settings(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "3001")),
        cors_allowed_origins=_csv(os.getenv("APP_CORS_ALLOWED_ORIGINS"))
        or ("http://localhost:8088", "http://localhost:5173"),
        demo_api_key=os.getenv("APP_DEMO_API_KEY", "local-demo-api-key"),
        demo_tenant_id=os.getenv("APP_DEMO_TENANT_ID", "public"),
        token_ttl_seconds=int(os.getenv("APP_TOKEN_TTL_SECONDS", "3600")),
        refresh_token_ttl_days=int(os.getenv("APP_JWT_REFRESH_EXPIRE_DAYS", "14")),
        jwt_secret=os.getenv("APP_JWT_SECRET", "local-python-jwt-secret-change-me"),
        rate_limit_per_minute=int(os.getenv("APP_RATE_LIMIT_PER_MINUTE", "120")),
        environment=os.getenv("APP_ENV", "development"),
        ingestion_queue_backend=os.getenv("APP_INGESTION_QUEUE_BACKEND", "memory"),
        redis_url=os.getenv("APP_REDIS_URL", "redis://localhost:6379/0"),
        vector_backend=os.getenv("APP_VECTOR_BACKEND", "simple"),
        database_url=os.getenv("APP_DATABASE_URL"),
        pgvector_url=os.getenv("APP_PGVECTOR_URL"),
        rabbitmq_url=os.getenv("APP_RABBITMQ_URL"),
        storage_backend=os.getenv("APP_STORAGE_BACKEND", "local"),
        storage_path=os.getenv("APP_STORAGE_PATH", str(Path(tempfile.gettempdir()) / "knowledgeops-files")),
        max_upload_bytes=int(os.getenv("APP_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        oidc_issuer_url=os.getenv("APP_OIDC_ISSUER_URL"),
        oidc_client_id=os.getenv("APP_OIDC_CLIENT_ID"),
        oidc_client_secret=os.getenv("APP_OIDC_CLIENT_SECRET"),
        oidc_redirect_uri=os.getenv("APP_OIDC_REDIRECT_URI"),
        model_base_url=os.getenv("APP_MODEL_BASE_URL"),
        model_api_key=os.getenv("APP_MODEL_API_KEY"),
        model_name=os.getenv("APP_MODEL_NAME", "qwen-plus"),
        reranker_backend=os.getenv("APP_RERANKER_BACKEND", "identity"),
        reranker_url=os.getenv("APP_RERANKER_URL"),
        allow_workspace_write=os.getenv("APP_ALLOW_WORKSPACE_WRITE", "false").lower() == "true",
        allow_workspace_shell=os.getenv("APP_ALLOW_WORKSPACE_SHELL", "false").lower() == "true",
    )
    settings.validate_startup()
    return settings


def _csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())
