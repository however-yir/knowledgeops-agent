from __future__ import annotations

from knowledgeops_py.scripts.shadow_preflight import validate_shadow_environment


def production_shadow_environment() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "APP_JWT_SECRET": "a" * 32,
        "APP_DEMO_API_KEY": "shadow-admin-key",
        "APP_DATABASE_URL": "mysql+aiomysql://shadow-mysql/knowledgeops_python",
        "APP_PGVECTOR_URL": "postgresql+asyncpg://shadow-pgvector/knowledgeops_python",
        "APP_REDIS_URL": "redis://shadow-redis/0",
        "APP_VECTOR_BACKEND": "pgvector",
        "APP_MODEL_BACKEND": "openai_compatible",
        "APP_MODEL_BASE_URL": "https://model.example.test/v1",
        "APP_MODEL_API_KEY": "shadow-model-key",
        "APP_RERANKER_BACKEND": "remote",
        "APP_RERANKER_URL": "https://reranker.example.test",
        "APP_INGESTION_QUEUE_BACKEND": "redis_stream",
        "APP_OIDC_ISSUER_URL": "https://idp.example.test",
        "APP_OIDC_CLIENT_ID": "knowledgeops-shadow",
        "APP_OIDC_REDIRECT_URI": "https://python-shadow.example.test/auth/oidc/callback",
        "SHADOW_JAVA_BASE_URL": "https://java-shadow.example.test",
        "SHADOW_PYTHON_BASE_URL": "https://python-shadow.example.test",
        "SHADOW_ISOLATED_DATABASE": "true",
        "SHADOW_READ_ONLY_MIRROR": "true",
        "SHADOW_WRITES_ISOLATED": "true",
        "SHADOW_REQUEST_TARGET": "10000",
    }


def test_shadow_preflight_accepts_a_production_ready_environment() -> None:
    assert validate_shadow_environment(production_shadow_environment()) == []

    seven_day_environment = production_shadow_environment()
    seven_day_environment.pop("SHADOW_REQUEST_TARGET")
    seven_day_environment["SHADOW_CONTINUOUS_DAYS"] = "7"
    assert validate_shadow_environment(seven_day_environment) == []


def test_shadow_preflight_reports_non_secret_isolation_and_target_failures() -> None:
    environment = production_shadow_environment()
    environment.pop("APP_OIDC_CLIENT_ID")
    environment["APP_INGESTION_QUEUE_BACKEND"] = "memory"
    environment["SHADOW_PYTHON_BASE_URL"] = environment["SHADOW_JAVA_BASE_URL"]
    environment["SHADOW_WRITES_ISOLATED"] = "false"
    environment["SHADOW_REQUEST_TARGET"] = "9999"

    failures = validate_shadow_environment(environment)

    assert "missing APP_OIDC_CLIENT_ID" in failures
    assert "APP_INGESTION_QUEUE_BACKEND must be redis_stream, rabbitmq or db_polling" in failures
    assert "SHADOW_JAVA_BASE_URL and SHADOW_PYTHON_BASE_URL must be different" in failures
    assert "SHADOW_WRITES_ISOLATED must be true" in failures
    assert "set SHADOW_REQUEST_TARGET to at least 10000 or SHADOW_CONTINUOUS_DAYS to at least 7" in failures


def test_shadow_preflight_does_not_report_store_equality_when_urls_are_missing() -> None:
    assert "APP_DATABASE_URL and APP_PGVECTOR_URL must use isolated stores" not in validate_shadow_environment({})
