"""034_sync_v2

Sync v2: cooperative cancellation + heartbeat-based stale-run recovery.

- cancel_requested: flag set by /ghl-sync/runs/{id}/cancel; the sync loop
  checks it between batches and exits cleanly
- last_heartbeat_at: written each batch by the sync loop; periodic sweeper
  reaps rows with stale heartbeats so the UI never shows a forever-running
  row again

Also recovers any row currently stuck in 'running' (impossible — the
process restarted to apply this migration, so any 'running' row is an
orphan from before the deploy).

Revision ID: 034
Revises: 033
"""
from alembic import op


revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ghl_sync_run ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE ghl_sync_run ADD COLUMN IF NOT EXISTS last_heartbeat_at TIMESTAMPTZ")
    op.execute("""
        UPDATE ghl_sync_run
        SET status = 'failed',
            completed_at = NOW(),
            duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at))::int,
            errors_count = errors_count + 1,
            error_details = COALESCE(error_details, '[]'::jsonb) || '[{"type":"orphaned","reason":"recovered_by_migration_034"}]'::jsonb
        WHERE status = 'running'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE ghl_sync_run DROP COLUMN IF EXISTS cancel_requested")
    op.execute("ALTER TABLE ghl_sync_run DROP COLUMN IF EXISTS last_heartbeat_at")
