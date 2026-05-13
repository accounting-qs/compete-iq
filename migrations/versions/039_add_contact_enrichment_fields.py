"""039_add_contact_enrichment_fields

Add enrichment fields to contacts table:
- enrichment_classification (TEXT)
- primary_identity (TEXT)
- characteristic (TEXT)
- sector (TEXT)

Revision ID: 039
Revises: 038
"""
from alembic import op


revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


COLUMNS = [
    ("enrichment_classification", "TEXT"),
    ("primary_identity", "TEXT"),
    ("characteristic", "TEXT"),
    ("sector", "TEXT"),
]


def upgrade() -> None:
    for name, typ in COLUMNS:
        op.execute(f"ALTER TABLE contacts ADD COLUMN IF NOT EXISTS {name} {typ}")


def downgrade() -> None:
    for name, _ in COLUMNS:
        op.execute(f"ALTER TABLE contacts DROP COLUMN IF EXISTS {name}")
