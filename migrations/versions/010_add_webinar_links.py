"""010_add_webinar_links

Add registration_link and unsubscribe_link columns to webinars table.

Revision ID: 010
Revises: 009
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("webinars", sa.Column("registration_link", sa.Text(), nullable=True))
    op.add_column("webinars", sa.Column("unsubscribe_link", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("webinars", "unsubscribe_link")
    op.drop_column("webinars", "registration_link")
