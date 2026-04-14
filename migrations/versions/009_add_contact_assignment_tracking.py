"""009_add_contact_assignment_tracking

Add assignment_id FK and outreach_status to contacts table.
- assignment_id: links a contact to a specific webinar list assignment
- outreach_status: 'available' → 'assigned' → 'used' lifecycle

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
    # assignment_id FK
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

    # outreach_status with default 'available'
    op.add_column(
        "contacts",
        sa.Column("outreach_status", sa.String(20), nullable=False, server_default="available"),
    )

    # assigned_date — the webinar date when the contact was assigned
    op.add_column(
        "contacts",
        sa.Column("assigned_date", sa.Date, nullable=True),
    )
    op.create_check_constraint(
        "ck_contacts_outreach_status",
        "contacts",
        "outreach_status IN ('available', 'assigned', 'used')",
    )

    # Indexes
    op.create_index("ix_contacts_assignment_id", "contacts", ["assignment_id"])
    op.create_index("ix_contacts_bucket_unassigned", "contacts", ["bucket_id", "assignment_id"])
    op.create_index("ix_contacts_outreach_status", "contacts", ["bucket_id", "outreach_status"])


def downgrade() -> None:
    op.drop_index("ix_contacts_outreach_status", table_name="contacts")
    op.drop_index("ix_contacts_bucket_unassigned", table_name="contacts")
    op.drop_index("ix_contacts_assignment_id", table_name="contacts")
    op.drop_constraint("ck_contacts_outreach_status", "contacts", type_="check")
    op.drop_column("contacts", "assigned_date")
    op.drop_column("contacts", "outreach_status")
    op.drop_constraint("fk_contacts_assignment_id", "contacts", type_="foreignkey")
    op.drop_column("contacts", "assignment_id")
