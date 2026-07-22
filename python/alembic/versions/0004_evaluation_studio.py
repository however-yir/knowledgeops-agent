"""Add durable evaluation dataset, case, and result records.

Revision ID: 0004_evaluation_studio
Revises: 0003_workflow_events
Create Date: 2026-07-22
"""

import sqlalchemy as sa
from alembic import op


revision = "0004_evaluation_studio"
down_revision = "0003_workflow_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return
    metadata = sa.MetaData()
    tables = {
        "py_evaluation_datasets": sa.Table(
            "py_evaluation_datasets",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("dataset_id", sa.String(length=64), nullable=False, index=True),
            sa.Column("tenant_id", sa.String(length=128), nullable=False, index=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.String(length=512)),
            sa.Column("baseline_run_id", sa.String(length=64)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("tenant_id", "dataset_id", name="uq_py_eval_dataset_tenant_dataset"),
        ),
        "py_evaluation_cases": sa.Table(
            "py_evaluation_cases",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("case_id", sa.String(length=64), nullable=False, index=True),
            sa.Column("dataset_id", sa.String(length=64), nullable=False, index=True),
            sa.Column("tenant_id", sa.String(length=128), nullable=False, index=True),
            sa.Column("category", sa.String(length=64)),
            sa.Column("chat_id", sa.String(length=128)),
            sa.Column("question_text", sa.Text(), nullable=False),
            sa.Column("expected_citations", sa.JSON(), nullable=False),
            sa.Column("expected_keywords", sa.JSON(), nullable=False),
            sa.Column("forbidden_keywords", sa.JSON(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("tenant_id", "dataset_id", "case_id", name="uq_py_eval_case_tenant_dataset_case"),
        ),
        "py_evaluation_results": sa.Table(
            "py_evaluation_results",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("result_id", sa.String(length=64), nullable=False, index=True),
            sa.Column("run_id", sa.String(length=64), nullable=False, index=True),
            sa.Column("dataset_id", sa.String(length=64), nullable=False, index=True),
            sa.Column("case_id", sa.String(length=64), nullable=False, index=True),
            sa.Column("tenant_id", sa.String(length=128), nullable=False, index=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("question_text", sa.Text(), nullable=False),
            sa.Column("answer_text", sa.Text()),
            sa.Column("citations", sa.JSON(), nullable=False),
            sa.Column("evidence", sa.JSON(), nullable=False),
            sa.Column("retrieval_hit", sa.Float(), nullable=False, server_default="0"),
            sa.Column("citation_coverage", sa.Float(), nullable=False, server_default="0"),
            sa.Column("keyword_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("answer_faithfulness", sa.Float(), nullable=False, server_default="0"),
            sa.Column("score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.String(length=1024)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("tenant_id", "result_id", name="uq_py_eval_result_tenant_result"),
        ),
    }
    inspector = sa.inspect(bind)
    for name, table in tables.items():
        if not inspector.has_table(name):
            table.create(bind=bind)

    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("py_evaluation_runs")}
    additions = (
        ("model_profile", sa.Column("model_profile", sa.String(length=32), nullable=False, server_default="balanced")),
        ("total_cases", sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0")),
        ("passed_cases", sa.Column("passed_cases", sa.Integer(), nullable=False, server_default="0")),
        ("run_score", sa.Column("run_score", sa.Float(), nullable=False, server_default="0")),
        ("retrieval_hit_rate", sa.Column("retrieval_hit_rate", sa.Float(), nullable=False, server_default="0")),
        ("citation_coverage_rate", sa.Column("citation_coverage_rate", sa.Float(), nullable=False, server_default="0")),
        ("answer_faithfulness_score", sa.Column("answer_faithfulness_score", sa.Float(), nullable=False, server_default="0")),
        ("avg_latency_ms", sa.Column("avg_latency_ms", sa.Float(), nullable=False, server_default="0")),
        ("failure_rate", sa.Column("failure_rate", sa.Float(), nullable=False, server_default="0")),
        ("error_message", sa.Column("error_message", sa.String(length=1024))),
        ("started_at", sa.Column("started_at", sa.DateTime(timezone=True))),
        ("finished_at", sa.Column("finished_at", sa.DateTime(timezone=True))),
        ("updated_at", sa.Column("updated_at", sa.DateTime(timezone=True))),
    )
    for name, column in additions:
        if name not in existing_columns:
            op.add_column("py_evaluation_runs", column)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        return
    op.drop_table("py_evaluation_results")
    op.drop_table("py_evaluation_cases")
    op.drop_table("py_evaluation_datasets")
    for column in (
        "updated_at",
        "finished_at",
        "started_at",
        "error_message",
        "failure_rate",
        "avg_latency_ms",
        "answer_faithfulness_score",
        "citation_coverage_rate",
        "retrieval_hit_rate",
        "run_score",
        "passed_cases",
        "total_cases",
        "model_profile",
    ):
        op.drop_column("py_evaluation_runs", column)
