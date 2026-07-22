"""Add durable Python workflow steps and events.

Revision ID: 0003_workflow_events
Revises: 0002_durable_ingestion
Create Date: 2026-07-22
"""

from alembic import op

from knowledgeops_py.infrastructure.models import WorkflowEventRecord, WorkflowStepRecord


revision = "0003_workflow_events"
down_revision = "0002_durable_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return
    WorkflowStepRecord.__table__.create(bind=bind, checkfirst=True)
    WorkflowEventRecord.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return
    WorkflowEventRecord.__table__.drop(bind=bind, checkfirst=True)
    WorkflowStepRecord.__table__.drop(bind=bind, checkfirst=True)
