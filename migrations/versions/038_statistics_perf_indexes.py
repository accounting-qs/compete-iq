"""038_statistics_perf_indexes

Indexes to make Statistics page fetches DB-bound instead of CPU-bound.

The per-webinar fetch ran 5+ full scans of ghl_contact (regex matches on
calendar_invite_response_history etc.) and built hash joins on LOWER(email)
across ghl_contact / contacts / webinargeek_subscribers — no functional or
trigram indexes existed.

This migration adds:
- pg_trgm extension (idempotent).
- GIN trgm indexes on the four ghl_contact text columns we regex-match.
- Functional LOWER(email) indexes on ghl_contact / contacts /
  webinargeek_subscribers so the cross-table joins can use them.
- ghl_webinar_stats.nj_count column to cache the per-webinar non-joiner
  count populated during sync (mirrors the existing gcal_invited_count).

Revision ID: 038
Revises: 037
"""
from alembic import op


revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pg_trgm powers GIN-indexed regex (~*) lookups on the calendar_* text
    # columns. Safe to run repeatedly.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── GIN trgm indexes for the regex-matched ghl_contact text columns ──
    # Every Statistics fetch runs `column ~* '\\yeN-Yes\\y'` style regex
    # against these four fields. With gin_trgm_ops Postgres can pick the
    # candidate rows by trigram before evaluating the regex.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ghl_contact_invite_response_history_trgm "
        "ON ghl_contact USING gin (calendar_invite_response_history gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ghl_contact_series_history_trgm "
        "ON ghl_contact USING gin (calendar_webinar_series_history gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ghl_contact_series_nj_trgm "
        "ON ghl_contact USING gin (calendar_webinar_series_non_joiners gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ghl_contact_invite_response_prefix_nj_trgm "
        "ON ghl_contact USING gin (calendar_invite_response_prefix_non_joiners gin_trgm_ops)"
    )

    # ── Functional LOWER(email) indexes for cross-table joins ────────────
    # All three statistics batches join `LOWER(g.email) = LOWER(c.email)` or
    # `LOWER(wgs.email) = LOWER(c.email)`; the existing plain `email` indexes
    # don't help because LOWER() is applied. The synthetic "planned" CTE
    # also anti-joins on LOWER(email).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ghl_contact_lower_email "
        "ON ghl_contact (LOWER(email))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_contacts_lower_email "
        "ON contacts (LOWER(email))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wg_subscribers_lower_email "
        "ON webinargeek_subscribers (LOWER(email))"
    )

    # ── nj_count cache column ────────────────────────────────────────────
    # Populated during the narrow phase of run_webinar_sync alongside
    # gcal_invited_count; the Statistics fetch reads it instead of
    # re-running the full-table regex scan for non-joiners.
    op.execute("ALTER TABLE ghl_webinar_stats ADD COLUMN IF NOT EXISTS nj_count INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE ghl_webinar_stats DROP COLUMN IF EXISTS nj_count")
    op.execute("DROP INDEX IF EXISTS ix_wg_subscribers_lower_email")
    op.execute("DROP INDEX IF EXISTS ix_contacts_lower_email")
    op.execute("DROP INDEX IF EXISTS ix_ghl_contact_lower_email")
    op.execute("DROP INDEX IF EXISTS ix_ghl_contact_invite_response_prefix_nj_trgm")
    op.execute("DROP INDEX IF EXISTS ix_ghl_contact_series_nj_trgm")
    op.execute("DROP INDEX IF EXISTS ix_ghl_contact_series_history_trgm")
    op.execute("DROP INDEX IF EXISTS ix_ghl_contact_invite_response_history_trgm")
    # Leave pg_trgm in place — other code may grow to rely on it.
