"""018_add_is_setup_to_assignments

Add is_setup boolean to webinar_list_assignments so senders can mark
a list as "set up in their outreach tool" — visible on the planning page.

Revision ID: 018
Revises: 017
"""
from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE webinar_list_assignments ADD COLUMN IF NOT EXISTS is_setup BOOLEAN NOT NULL DEFAULT false")


def downgrade() -> None:
    op.drop_column("webinar_list_assignments", "is_setup")
