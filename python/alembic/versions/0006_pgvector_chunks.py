"""Add an additive pgvector projection for Python ingestion chunks.

Revision ID: 0006_pgvector_chunks
Revises: 0005_graph_store
Create Date: 2026-07-22
"""

from alembic import op

revision = "0006_pgvector_chunks"
down_revision = "0005_graph_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS py_pgvector_chunks (
            chunk_id varchar(64) PRIMARY KEY,
            tenant_id varchar(128) NOT NULL,
            chat_id varchar(128) NOT NULL,
            source_name varchar(512) NOT NULL,
            chunk_index integer NOT NULL,
            content text NOT NULL,
            embedding vector(1024) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_py_pgvector_chunks_tenant_chat ON py_pgvector_chunks (tenant_id, chat_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_py_pgvector_chunks_embedding_hnsw "
        "ON py_pgvector_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS py_pgvector_chunks")
