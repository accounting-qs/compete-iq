"""017_add_bucket_merged_into

Add a merged_into_bucket_id pointer to outreach_buckets so that when a
bucket is soft-deleted as part of a merge, future CSV imports with its
original name automatically redirect new contacts to the keeper bucket.

Revision ID: 017
Revises: 016
"""
from alembic import op


revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Disable the session statement_timeout — Supabase's default kills DDL
    # that briefly waits on a table-level lock. DDL on outreach_buckets is
    # still O(1) (nullable column, no scan) once the lock is acquired.
    op.execute("SET statement_timeout = 0")
    op.execute("SET lock_timeout = 0")

    # Step 1: add nullable column (O(1) in Postgres 11+)
    op.execute("ALTER TABLE outreach_buckets ADD COLUMN IF NOT EXISTS merged_into_bucket_id UUID")

    # Step 2: add FK as NOT VALID to skip scanning existing rows (all NULL anyway)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_outreach_buckets_merged_into'
            ) THEN
                ALTER TABLE outreach_buckets
                ADD CONSTRAINT fk_outreach_buckets_merged_into
                FOREIGN KEY (merged_into_bucket_id)
                REFERENCES outreach_buckets(id) ON DELETE SET NULL
                NOT VALID;
            END IF;
        END $$;
    """)

    # Step 3: partial index on non-null values (fast — no existing non-null rows)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_outreach_buckets_merged_into "
        "ON outreach_buckets (merged_into_bucket_id) "
        "WHERE merged_into_bucket_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_outreach_buckets_merged_into")
    op.execute("ALTER TABLE outreach_buckets DROP CONSTRAINT IF EXISTS fk_outreach_buckets_merged_into")
    op.execute("ALTER TABLE outreach_buckets DROP COLUMN IF EXISTS merged_into_bucket_id")
