from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from docker.errors import DockerException
from sqlalchemy import update
from sqlalchemy.engine import make_url
from testcontainers.mysql import MySqlContainer

from alembic import command
from knowledgeops_py.infrastructure.database import create_engine, create_session_factory
from knowledgeops_py.infrastructure.ingestion_repository import SqlAlchemyIngestionRepository, utc_now
from knowledgeops_py.infrastructure.models import IngestionJobRecord


def test_mysql_alembic_and_skip_locked_claims_are_durable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TESTCONTAINERS_RYUK_DISABLED", "true")
    try:
        with MySqlContainer(
            "mysql:8.0.36",
            username="knowledgeops",
            password="knowledgeops",
            dbname="knowledgeops",
        ).with_command("--default-authentication-plugin=mysql_native_password") as container:
            database_url = make_url(container.get_connection_url()).set(drivername="mysql+aiomysql").render_as_string(
                hide_password=False
            )
            monkeypatch.setenv("APP_DATABASE_URL", database_url)
            command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")

            async def verify() -> None:
                engine = create_engine(database_url)
                repository = SqlAlchemyIngestionRepository(create_session_factory(engine))
                first = await repository.create(job("job_mysql_a", "tenant-a", "key-a"))
                second = await repository.create(job("job_mysql_b", "tenant-b", "key-b"))
                duplicate = await repository.create(job("job_mysql_duplicate", "tenant-b", "key-b"))
                assert duplicate.job_id == second.job_id
                claims = await asyncio.gather(repository.claim_next(), repository.claim_next())
                claimed_ids = {claim.job_id for claim in claims if claim is not None}
                assert claimed_ids <= {first.job_id, second.job_id}
                while len(claimed_ids) < 2:
                    remaining = await repository.claim_next()
                    assert remaining is not None
                    claimed_ids.add(remaining.job_id)
                assert claimed_ids == {first.job_id, second.job_id}
                assert await repository.get("tenant-a", second.job_id) is None
                async with engine.begin() as connection:
                    await connection.execute(
                        update(IngestionJobRecord)
                        .where(IngestionJobRecord.job_id.in_([first.job_id, second.job_id]))
                        .values(started_at=utc_now() - timedelta(seconds=10))
                    )
                assert await repository.recover_abandoned(lease_seconds=1) == 2
                assert (await repository.get("tenant-a", first.job_id)).status == "RETRY"  # type: ignore[union-attr]
                assert (await repository.get("tenant-b", second.job_id)).status == "RETRY"  # type: ignore[union-attr]
                await engine.dispose()

            asyncio.run(verify())
    except DockerException as exc:
        detail = str(exc)
        if not os.getenv("CI") and ("registry-1.docker.io" in detail or "No such image: mysql:" in detail):
            pytest.skip("Docker Hub is unavailable for the local MySQL Testcontainer")
        raise


def job(job_id: str, tenant_id: str, idempotency_key: str) -> IngestionJobRecord:
    return IngestionJobRecord(
        job_id=job_id,
        tenant_id=tenant_id,
        chat_id="chat-a",
        source_type="FILE",
        source_name="policy.txt",
        file_path=None,
        status="QUEUED",
        idempotency_key=idempotency_key,
        max_retries=2,
        trace_id="trace",
        queue_backend="db_polling",
        payload={},
    )
