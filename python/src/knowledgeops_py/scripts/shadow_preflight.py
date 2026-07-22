"""Fail fast when an external shadow-validation environment is incomplete."""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlparse


def validate_shadow_environment(environment: Mapping[str, str]) -> list[str]:
    """Return non-secret validation failures for the Python shadow environment."""
    failures: list[str] = []
    required = (
        "APP_JWT_SECRET",
        "APP_DEMO_API_KEY",
        "APP_DATABASE_URL",
        "APP_PGVECTOR_URL",
        "APP_REDIS_URL",
        "APP_MODEL_BACKEND",
        "APP_RERANKER_BACKEND",
        "APP_OIDC_ISSUER_URL",
        "APP_OIDC_CLIENT_ID",
        "APP_OIDC_REDIRECT_URI",
        "SHADOW_JAVA_BASE_URL",
        "SHADOW_PYTHON_BASE_URL",
    )
    for name in required:
        if not environment.get(name, "").strip():
            failures.append(f"missing {name}")

    if environment.get("APP_ENV", "").lower() not in {"production", "prod"}:
        failures.append("APP_ENV must be production for shadow validation")
    if environment.get("APP_JWT_SECRET") in {"", "local-python-jwt-secret-change-me", "replace-me-with-real-secret"}:
        failures.append("APP_JWT_SECRET must not use a development default")
    if environment.get("APP_DEMO_API_KEY") == "local-demo-api-key":
        failures.append("APP_DEMO_API_KEY must not use a development default")
    if environment.get("APP_VECTOR_BACKEND") != "pgvector":
        failures.append("APP_VECTOR_BACKEND must be pgvector")
    if environment.get("APP_DATABASE_URL") and environment.get("APP_PGVECTOR_URL") and environment.get("APP_DATABASE_URL") == environment.get("APP_PGVECTOR_URL"):
        failures.append("APP_DATABASE_URL and APP_PGVECTOR_URL must use isolated stores")

    model_backend = environment.get("APP_MODEL_BACKEND", "")
    if model_backend == "openai_compatible":
        for name in ("APP_MODEL_BASE_URL", "APP_MODEL_API_KEY"):
            if not environment.get(name, "").strip():
                failures.append(f"missing {name} for openai_compatible model backend")
    elif model_backend == "ollama":
        if not environment.get("APP_OLLAMA_BASE_URL", "").strip():
            failures.append("missing APP_OLLAMA_BASE_URL for ollama model backend")
    elif model_backend:
        failures.append("APP_MODEL_BACKEND must be openai_compatible or ollama")

    reranker_backend = environment.get("APP_RERANKER_BACKEND", "")
    if reranker_backend == "remote" and not environment.get("APP_RERANKER_URL", "").strip():
        failures.append("missing APP_RERANKER_URL for remote reranker")
    elif reranker_backend == "local" and not environment.get("APP_RERANKER_MODEL", "").strip():
        failures.append("missing APP_RERANKER_MODEL for local reranker")
    elif reranker_backend and reranker_backend not in {"remote", "local"}:
        failures.append("APP_RERANKER_BACKEND must be remote or local")

    queue_backend = environment.get("APP_INGESTION_QUEUE_BACKEND", "")
    if queue_backend not in {"redis_stream", "rabbitmq", "db_polling"}:
        failures.append("APP_INGESTION_QUEUE_BACKEND must be redis_stream, rabbitmq or db_polling")
    if queue_backend == "rabbitmq" and not environment.get("APP_RABBITMQ_URL", "").strip():
        failures.append("missing APP_RABBITMQ_URL for rabbitmq ingestion")

    for name in ("SHADOW_ISOLATED_DATABASE", "SHADOW_READ_ONLY_MIRROR", "SHADOW_WRITES_ISOLATED"):
        if environment.get(name, "").lower() != "true":
            failures.append(f"{name} must be true")
    failures.extend(_endpoint_failures(environment))
    failures.extend(_observation_target_failures(environment))
    return failures


def _endpoint_failures(environment: Mapping[str, str]) -> list[str]:
    java_url = environment.get("SHADOW_JAVA_BASE_URL", "")
    python_url = environment.get("SHADOW_PYTHON_BASE_URL", "")
    failures = [f"{name} must be an absolute http(s) URL" for name, value in (
        ("SHADOW_JAVA_BASE_URL", java_url),
        ("SHADOW_PYTHON_BASE_URL", python_url),
    ) if value and not _is_http_url(value)]
    if java_url and python_url and java_url.rstrip("/") == python_url.rstrip("/"):
        failures.append("SHADOW_JAVA_BASE_URL and SHADOW_PYTHON_BASE_URL must be different")
    return failures


def _observation_target_failures(environment: Mapping[str, str]) -> list[str]:
    requests = _nonnegative_integer(environment, "SHADOW_REQUEST_TARGET")
    days = _nonnegative_integer(environment, "SHADOW_CONTINUOUS_DAYS")
    failures: list[str] = []
    if requests is None and days is None:
        return ["set SHADOW_REQUEST_TARGET to at least 10000 or SHADOW_CONTINUOUS_DAYS to at least 7"]
    if requests is not None and requests < 10_000 and (days is None or days < 7):
        failures.append("set SHADOW_REQUEST_TARGET to at least 10000 or SHADOW_CONTINUOUS_DAYS to at least 7")
    return failures


def _nonnegative_integer(environment: Mapping[str, str], name: str) -> int | None:
    value = environment.get(name, "").strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def main() -> None:
    failures = validate_shadow_environment(os.environ)
    if failures:
        raise SystemExit("shadow preflight failed:\n" + "\n".join(f"- {failure}" for failure in failures))
    print("python shadow preflight ok: production dependencies and isolation declarations are present")


if __name__ == "__main__":
    main()
