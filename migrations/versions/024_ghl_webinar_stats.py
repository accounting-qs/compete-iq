"""024_ghl_webinar_stats

Per-webinar count cache. Stores the `gcalInvitedGhl` count (total contacts
whose `calendar_webinar_series_history` contains eN) without requiring us
to sync all 200k+ rows per webinar. Populated during webinar sync from
a single GHL search with pageLimit=1.

Revision ID: 024
Revises: 023
"""
from alembic import op


revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ghl_webinar_stats (
            webinar_number INTEGER PRIMARY KEY,
            gcal_invited_count INTEGER,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ghl_webinar_stats")
