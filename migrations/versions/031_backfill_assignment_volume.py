"""031_backfill_assignment_volume

Recompute `webinar_list_assignments.volume` from the actual count of
contacts attached to each assignment (status in 'assigned' or 'used').

Prior to this, `volume` was set to the *requested* slice size at
creation and never adjusted. When the bucket was already drained or a
concurrent assignment lost the race, fewer (or zero) contacts ended up
with `assignment_id` pointing at the row, but `volume` still advertised
the requested number. The Planning table and contacts page header both
read this stale snapshot, while the per-status counts read the real
attached rows — so the totals diverged (e.g. header "10,000 total" but
All tab "0").

Revision ID: 031
Revises: 030
"""
from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Set volume = count of attached contacts (assigned + used).
    op.execute("""
        UPDATE webinar_list_assignments a
        SET volume = COALESCE(sub.cnt, 0)
        FROM (
            SELECT assignment_id, COUNT(*) AS cnt
            FROM contacts
            WHERE assignment_id IS NOT NULL
              AND outreach_status IN ('assigned', 'used')
            GROUP BY assignment_id
        ) sub
        WHERE a.id = sub.assignment_id
    """)
    # Assignments with no attached contacts at all aren't covered by the
    # join above — zero them out explicitly.
    op.execute("""
        UPDATE webinar_list_assignments a
        SET volume = 0
        WHERE NOT EXISTS (
            SELECT 1 FROM contacts c
            WHERE c.assignment_id = a.id
              AND c.outreach_status IN ('assigned', 'used')
        )
    """)


def downgrade() -> None:
    # No-op: the pre-migration `volume` values cannot be reconstructed.
    pass
