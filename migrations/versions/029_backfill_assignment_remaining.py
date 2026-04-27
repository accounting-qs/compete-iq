"""029_backfill_assignment_remaining

Recompute `webinar_list_assignments.remaining` from the current
`contacts.outreach_status` state. Prior to this, `remaining` was set to
`volume` at assignment creation and never decremented when contacts were
marked used, so the Planning page's "remaining" column was stale for any
assignment where contacts had already been used.

Revision ID: 029
Revises: 028
"""
from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE webinar_list_assignments a
        SET remaining = COALESCE(sub.cnt, 0)
        FROM (
            SELECT assignment_id, COUNT(*) AS cnt
            FROM contacts
            WHERE assignment_id IS NOT NULL
              AND outreach_status = 'assigned'
            GROUP BY assignment_id
        ) sub
        WHERE a.id = sub.assignment_id
    """)
    # Assignments with zero still-assigned contacts (all used or none claimed)
    # aren't covered by the join above — reset those to 0 explicitly.
    op.execute("""
        UPDATE webinar_list_assignments a
        SET remaining = 0
        WHERE NOT EXISTS (
            SELECT 1 FROM contacts c
            WHERE c.assignment_id = a.id
              AND c.outreach_status = 'assigned'
        )
    """)


def downgrade() -> None:
    # No-op: the pre-migration `remaining` values cannot be reconstructed.
    pass
