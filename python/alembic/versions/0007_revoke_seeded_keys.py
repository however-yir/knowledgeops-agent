"""Revoke seeded demo API keys (Java V15 parity).

Revision ID: 0007_revoke_seeded_keys
Revises: 0006_pgvector_chunks
Create Date: 2026-08-28

Mirrors Java V15__revoke_seeded_demo_api_keys: credentials whose plaintext is
committed to the repository (Python seed key "local-demo-api-key") must not
stay enabled in databases that already received them. Runtime seeding of the
key is disabled in production by the same change.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_revoke_seeded_keys"
down_revision = "0006_pgvector_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "py_api_keys" not in inspector.get_table_names():
        # On PostgreSQL deployments the py_* baseline tables are provisioned
        # outside Alembic; nothing seeded means nothing to revoke.
        return
    op.execute(
        sa.text(
            "UPDATE py_api_keys SET enabled = :enabled, revoked_at = CURRENT_TIMESTAMP, "
            "revoked_reason = :reason WHERE key_name = 'local-demo' AND enabled = :was_enabled"
        ).bindparams(
            enabled=False,
            was_enabled=True,
            reason="seeded credential revoked (Java V15 parity)",
        )
    )


def downgrade() -> None:
    # Irreversible by design: plaintext seed credentials must not be restored.
    return None
