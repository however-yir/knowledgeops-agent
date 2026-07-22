"""Add durable ingestion metadata and document chunk storage.

Revision ID: 0002_durable_ingestion
Revises: 0001_java_v14_baseline
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa

from knowledgeops_py.infrastructure.models import IngestionChunkRecord


revision = "0002_durable_ingestion"
down_revision = "0001_java_v14_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("py_ingestion_jobs")}
    additions = [
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("queue_backend", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for column in additions:
        if column.name not in existing_columns:
            op.add_column("py_ingestion_jobs", column)
    if "py_ingestion_chunks" not in inspector.get_table_names():
        IngestionChunkRecord.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return
    inspector = sa.inspect(bind)
    if "py_ingestion_chunks" in inspector.get_table_names():
        IngestionChunkRecord.__table__.drop(bind=bind, checkfirst=True)
