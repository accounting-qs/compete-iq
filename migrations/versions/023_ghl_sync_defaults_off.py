"""023_ghl_sync_defaults_off

Disable automatic GHL syncs by default. Also flips the already-seeded
singleton row to disabled so an existing DB picks up the new default.

Revision ID: 023
Revises: 022
"""
from alembic import op


revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ghl_sync_settings
          ALTER COLUMN incremental_enabled SET DEFAULT FALSE,
          ALTER COLUMN weekly_full_enabled SET DEFAULT FALSE
    """)
    # Flip the already-seeded row too (manual trigger only until user opts in)
    op.execute("""
        UPDATE ghl_sync_settings
        SET incremental_enabled = FALSE,
            weekly_full_enabled = FALSE,
            updated_at = now()
        WHERE id = 1
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE ghl_sync_settings
          ALTER COLUMN incremental_enabled SET DEFAULT TRUE,
          ALTER COLUMN weekly_full_enabled SET DEFAULT TRUE
    """)
