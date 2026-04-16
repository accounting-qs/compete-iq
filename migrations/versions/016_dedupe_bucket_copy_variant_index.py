"""016_dedupe_bucket_copy_variant_index

Two concurrent generate/regenerate calls (or a falsy-zero bug in
`max(variant_index) or -1`) could assign the same `variant_index` to
multiple live `bucket_copies` rows in the same (bucket_id, copy_type)
group. The UI shows these as duplicate "V1", "V2", etc.

This migration:
  1. Renumbers live (deleted_at IS NULL) rows so each (bucket_id,
     copy_type) group has unique sequential indices starting at 0.
     Ordering by (variant_index, created_at, id) keeps existing
     V-numbers as stable as possible. `is_primary` and
     `primary_picked_by_user` are NEVER touched, so the user's
     selected variant remains selected.
  2. Adds a partial unique index to prevent the bug from recurring.
     Soft-deleted rows are excluded from the constraint so historical
     duplicates among deleted rows don't block the upgrade.

Revision ID: 016
Revises: 015
"""
from alembic import op


revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        WITH renumbered AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY bucket_id, copy_type
                    ORDER BY variant_index, created_at, id
                ) - 1 AS new_idx
            FROM bucket_copies
            WHERE deleted_at IS NULL
        )
        UPDATE bucket_copies bc
        SET variant_index = renumbered.new_idx
        FROM renumbered
        WHERE bc.id = renumbered.id
          AND bc.variant_index <> renumbered.new_idx;
    """)

    op.create_index(
        "ux_bucket_copies_bucket_type_idx_live",
        "bucket_copies",
        ["bucket_id", "copy_type", "variant_index"],
        unique=True,
        postgresql_where="deleted_at IS NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "ux_bucket_copies_bucket_type_idx_live",
        table_name="bucket_copies",
        postgresql_where="deleted_at IS NULL",
    )
