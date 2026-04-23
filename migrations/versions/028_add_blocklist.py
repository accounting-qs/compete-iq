"""028_add_blocklist

Blocklist of emails excluded from outreach (GHL DND, WebinarGeek unsubscribed,
manual, CSV). Dedupe per user via unique (user_id, email); emails stored lowercased.

Revision ID: 028
Revises: 027
"""
from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS blocklist (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL,
            email TEXT NOT NULL,
            source VARCHAR(20) NOT NULL,
            reason TEXT,
            source_ref TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_blocklist_user_email UNIQUE (user_id, email)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_blocklist_email ON blocklist (email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_blocklist_user ON blocklist (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS blocklist")
