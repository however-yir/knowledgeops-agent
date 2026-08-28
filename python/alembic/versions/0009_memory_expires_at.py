"""Add expiring memories (Java parity: d91405b expires_at filtering).

Revision ID: 0009_memory_expires_at
Revises: 0008_workflow_step_tokens
Create Date: 2026-08-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_memory_expires_at"
down_revision = "0008_workflow_step_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "py_memory_items" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("py_memory_items")}
    if "expires_at" not in existing_columns:
        op.add_column("py_memory_items", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "py_memory_items" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("py_memory_items")}
    if "expires_at" in existing_columns:
        op.drop_column("py_memory_items", "expires_at")
