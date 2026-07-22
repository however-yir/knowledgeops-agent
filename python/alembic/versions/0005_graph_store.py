"""Add durable graph relations and facts.

Revision ID: 0005_graph_store
Revises: 0004_evaluation_studio
Create Date: 2026-07-22
"""

import sqlalchemy as sa
from alembic import op


revision = "0005_graph_store"
down_revision = "0004_evaluation_studio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return
    metadata = sa.MetaData()
    relations = sa.Table(
        "py_graph_relations",
        metadata,
        sa.Column("relation_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False, index=True),
        sa.Column("source_entity_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("target_entity_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("evidence_id", sa.String(length=128)),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    facts = sa.Table(
        "py_graph_facts",
        metadata,
        sa.Column("fact_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False, index=True),
        sa.Column("subject", sa.String(length=255), nullable=False, index=True),
        sa.Column("predicate", sa.String(length=255), nullable=False, index=True),
        sa.Column("object", sa.String(length=512), nullable=False),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_to", sa.Date()),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("source", sa.String(length=255)),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    inspector = sa.inspect(bind)
    if not inspector.has_table(relations.name):
        relations.create(bind=bind)
    if not inspector.has_table(facts.name):
        facts.create(bind=bind)

    existing = {column["name"] for column in sa.inspect(bind).get_columns("py_graph_entities")}
    additions = (
        ("aliases", sa.Column("aliases", sa.JSON())),
        ("description", sa.Column("description", sa.Text())),
        ("source_id", sa.Column("source_id", sa.String(length=128))),
        ("updated_at", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))),
    )
    for name, column in additions:
        if name not in existing:
            op.add_column("py_graph_entities", column)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        return
    op.drop_table("py_graph_facts")
    op.drop_table("py_graph_relations")
    for column in ("updated_at", "source_id", "description", "aliases"):
        op.drop_column("py_graph_entities", column)
