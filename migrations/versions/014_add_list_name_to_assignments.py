"""014_add_list_name_to_assignments

Add a custom list_name column to webinar_list_assignments so users
can define a custom name per assignment row.

Revision ID: 014
Revises: 013
"""
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE webinar_list_assignments ADD COLUMN IF NOT EXISTS list_name TEXT")


def downgrade() -> None:
    op.drop_column("webinar_list_assignments", "list_name")
