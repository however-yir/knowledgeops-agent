"""Seed-credential hygiene tests (Java V15 parity: revoke seeded API keys)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from knowledgeops_py.app import seed_store
from knowledgeops_py.config import Settings
from knowledgeops_py.domain.runtime import PlatformStore


def test_seed_demo_credentials_property() -> None:
    assert Settings().seed_demo_credentials is True
    assert Settings(environment="production").seed_demo_credentials is False


def test_seed_store_skips_api_key_in_production() -> None:
    store = PlatformStore()
    seed_store(store, Settings(environment="production", demo_api_key="custom-prod-key", demo_tenant_id="tenant-a"))
    assert store.api_keys == {}
    # Non-credential seeding keeps working so evaluation tooling stays usable.
    assert "default" in store.eval_datasets
    assert store.budgets


def test_seed_store_seeds_api_key_outside_production() -> None:
    store = PlatformStore()
    seed_store(store, Settings(demo_api_key="test-key", demo_tenant_id="tenant-a"))
    assert len(store.api_keys) == 1
    record = next(iter(store.api_keys.values()))
    assert record["keyName"] == "local-demo"
    assert record["role"] == "ADMIN"


def test_validate_startup_rejects_default_demo_key_in_production() -> None:
    settings = Settings(
        environment="production",
        jwt_secret="a-validly-configured-secret",
        demo_api_key="local-demo-api-key",
    )
    with pytest.raises(ValueError, match="APP_DEMO_API_KEY"):
        settings.validate_startup()


def _alembic_config(db_url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def _seeded_key_row(db_path: Path) -> None:
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO py_api_keys (key_hash, key_name, role, enabled, tenant_id, created_at, updated_at) "
                "VALUES ('seedhash', 'local-demo', 'ADMIN', 1, 'public', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()


def test_alembic_head_revokes_seeded_demo_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "parity-seed.db"
    monkeypatch.setenv("APP_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    config = _alembic_config(f"sqlite+aiosqlite:///{db_path}")

    command.upgrade(config, "0006_pgvector_chunks")
    _seeded_key_row(db_path)
    command.upgrade(config, "head")

    conn = sqlite3.connect(db_path)
    try:
        row: Any = conn.execute("SELECT enabled, revoked_reason FROM py_api_keys WHERE key_name = 'local-demo'").fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == 0
    assert "seeded credential revoked" in row[1]


def test_alembic_head_upgrade_is_clean_from_scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "parity-fresh.db"
    monkeypatch.setenv("APP_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(_alembic_config(f"sqlite+aiosqlite:///{db_path}"), "head")

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM py_api_keys WHERE key_name = 'local-demo'").fetchone()[0]
    finally:
        conn.close()
    assert count == 0
