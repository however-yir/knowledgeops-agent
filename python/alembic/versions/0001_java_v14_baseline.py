"""Additive Python persistence baseline mapped to Java Flyway V1-V14 domains.

Revision ID: 0001_java_v14_baseline
Revises:
Create Date: 2026-07-22
"""

from alembic import op

from knowledgeops_py.infrastructure.models import Base


revision = "0001_java_v14_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        return
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        return
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
