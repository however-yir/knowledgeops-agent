"""Persist per-step token usage on workflow steps (Java 60a69da parity).

Revision ID: 0008_workflow_step_tokens
Revises: 0007_revoke_seeded_keys
Create Date: 2026-08-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_workflow_step_tokens"
down_revision = "0007_revoke_seeded_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "py_workflow_steps" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("py_workflow_steps")}
    additions = [
        sa.Column("input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("output_tokens", sa.BigInteger(), nullable=True),
    ]
    for column in additions:
        if column.name not in existing_columns:
            op.add_column("py_workflow_steps", column)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "py_workflow_steps" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("py_workflow_steps")}
    for name in ("input_tokens", "output_tokens"):
        if name in existing_columns:
            op.drop_column("py_workflow_steps", name)
