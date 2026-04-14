"""009_add_contact_assignment_tracking

Add assignment_id FK to contacts table so we track which specific contacts
are assigned to which webinar list assignment. Prevents double-assigning
the same contact to multiple senders.

Revision ID: 009
Revises: 008
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("assignment_id", sa.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_contacts_assignment_id",
        "contacts",
        "webinar_list_assignments",
        ["assignment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_contacts_assignment_id", "contacts", ["assignment_id"])
    # Composite index for fast "unassigned contacts in bucket" queries
    op.create_index("ix_contacts_bucket_unassigned", "contacts", ["bucket_id", "assignment_id"])


def downgrade() -> None:
    op.drop_index("ix_contacts_bucket_unassigned", table_name="contacts")
    op.drop_index("ix_contacts_assignment_id", table_name="contacts")
    op.drop_constraint("fk_contacts_assignment_id", "contacts", type_="foreignkey")
    op.drop_column("contacts", "assignment_id")
