from __future__ import annotations

import json
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
    pgvector_dimensions: int = 1024
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
    model_backend: str = "openai_compatible"
    model_name: str = "qwen-plus"
    embedding_model: str = "text-embedding-v4"
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen3:1.7b"
    ollama_embedding_model: str = "nomic-embed-text"
    reranker_backend: str = "identity"
    reranker_url: str | None = None
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    trusted_runtime_enabled: bool = False
    trusted_runtime_disabled_actions: tuple[str, ...] = ()
    trusted_runtime_tenant_allowed_actions: dict[str, tuple[str, ...]] = field(default_factory=dict)
    workspace_root: str = "."
    allow_workspace_write: bool = False
    allow_workspace_shell: bool = False
    workspace_command_timeout_seconds: int = 10
    workspace_max_command_output_bytes: int = 12_000
    workspace_max_file_bytes: int = 20_000
    workspace_max_search_files: int = 1_000
    workspace_allowed_commands: tuple[str, ...] = ("pwd", "ls", "rg", "git", "mvn")
    workspace_allowed_git_subcommands: tuple[str, ...] = ("status", "diff", "show", "log", "rev-parse", "branch")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def seed_demo_credentials(self) -> bool:
        """Whether the well-known local demo API key may be seeded at startup.

        The demo key plaintext is committed to the repository, so production
        never seeds it (Java parity: V15 revokes seeded credentials and the
        startup validator forbids the development default).
        """
        return not self.is_production

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
        if self.vector_backend != "pgvector" or not self.pgvector_url:
            raise ValueError("APP_VECTOR_BACKEND=pgvector and APP_PGVECTOR_URL are required in production")
        if not self.redis_url:
            raise ValueError("APP_REDIS_URL is required in production")
        if self.ingestion_queue_backend not in {"redis_stream", "rabbitmq", "db_polling"}:
            raise ValueError(
                "APP_INGESTION_QUEUE_BACKEND must be redis_stream, rabbitmq or db_polling in production"
            )
        if self.ingestion_queue_backend == "rabbitmq" and not self.rabbitmq_url:
            raise ValueError("APP_RABBITMQ_URL is required for rabbitmq ingestion in production")
        if self.model_backend not in {"openai_compatible", "ollama"}:
            raise ValueError("APP_MODEL_BACKEND must be openai_compatible or ollama")
        if self.model_backend == "openai_compatible" and (not self.model_base_url or not self.model_api_key):
            raise ValueError("APP_MODEL_BASE_URL and APP_MODEL_API_KEY are required in production")
        if self.model_backend == "ollama" and not self.ollama_base_url:
            raise ValueError("APP_OLLAMA_BASE_URL is required for the Ollama production provider")
        if self.reranker_backend == "identity":
            raise ValueError("APP_RERANKER_BACKEND cannot be identity in production")
        if self.reranker_backend not in {"remote", "local"}:
            raise ValueError("APP_RERANKER_BACKEND must be remote or local in production")
        if self.reranker_backend == "remote" and not self.reranker_url:
            raise ValueError("APP_RERANKER_URL is required for the remote production reranker")
        if self.reranker_backend == "local" and not self.reranker_model:
            raise ValueError("APP_RERANKER_MODEL is required for the local production reranker")
        if self.pgvector_dimensions <= 0:
            raise ValueError("APP_PGVECTOR_DIMENSIONS must be positive")


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
        pgvector_dimensions=int(os.getenv("APP_PGVECTOR_DIMENSIONS", "1024")),
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
        model_backend=os.getenv("APP_MODEL_BACKEND", "openai_compatible"),
        model_name=os.getenv("APP_MODEL_NAME", "qwen-plus"),
        embedding_model=os.getenv("APP_EMBEDDING_MODEL", "text-embedding-v4"),
        ollama_base_url=os.getenv("APP_OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_chat_model=os.getenv("APP_OLLAMA_CHAT_MODEL", "qwen3:1.7b"),
        ollama_embedding_model=os.getenv("APP_OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
        reranker_backend=os.getenv("APP_RERANKER_BACKEND", "identity"),
        reranker_url=os.getenv("APP_RERANKER_URL"),
        reranker_model=os.getenv("APP_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"),
        trusted_runtime_enabled=os.getenv("APP_AGENT_HARNESS_TRUSTED_ENABLED", "false").lower() == "true",
        trusted_runtime_disabled_actions=_csv(os.getenv("APP_AGENT_HARNESS_DISABLED_ACTIONS")),
        trusted_runtime_tenant_allowed_actions=_tenant_allowed_actions(os.getenv("APP_AGENT_HARNESS_TENANT_ALLOWED_ACTIONS")),
        workspace_root=os.getenv("APP_AGENT_HARNESS_WORKSPACE_ROOT", "."),
        allow_workspace_write=os.getenv(
            "APP_AGENT_HARNESS_WORKSPACE_WRITE_ENABLED", os.getenv("APP_ALLOW_WORKSPACE_WRITE", "false")
        ).lower() == "true",
        allow_workspace_shell=os.getenv(
            "APP_AGENT_HARNESS_WORKSPACE_SHELL_ENABLED", os.getenv("APP_ALLOW_WORKSPACE_SHELL", "false")
        ).lower() == "true",
        workspace_command_timeout_seconds=int(os.getenv("APP_AGENT_HARNESS_COMMAND_TIMEOUT_SECONDS", "10")),
        workspace_max_command_output_bytes=int(os.getenv("APP_AGENT_HARNESS_MAX_COMMAND_OUTPUT_BYTES", "12000")),
        workspace_max_file_bytes=int(os.getenv("APP_AGENT_HARNESS_MAX_FILE_BYTES", "20000")),
        workspace_max_search_files=int(os.getenv("APP_AGENT_HARNESS_MAX_SEARCH_FILES", "1000")),
        workspace_allowed_commands=_csv(os.getenv("APP_AGENT_HARNESS_ALLOWED_COMMANDS")) or ("pwd", "ls", "rg", "git", "mvn"),
        workspace_allowed_git_subcommands=_csv(os.getenv("APP_AGENT_HARNESS_ALLOWED_GIT_SUBCOMMANDS"))
        or ("status", "diff", "show", "log", "rev-parse", "branch"),
    )
    settings.validate_startup()
    return settings


def _csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _tenant_allowed_actions(value: str | None) -> dict[str, tuple[str, ...]]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(tenant): tuple(str(action) for action in actions if str(action).strip())
        for tenant, actions in parsed.items()
        if isinstance(actions, list)
    }
