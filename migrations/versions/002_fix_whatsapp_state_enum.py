"""Fix whatsapp_session_state enum — add 'searching' and 'awaiting_handle'

These states are used by services/webhook.py but were missing from the DB
enum, causing a constraint violation on every WhatsApp URL message.

Revision ID: 002
Revises: 001
Create Date: 2026-03-27
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL supports ADD VALUE IF NOT EXISTS — safe to run multiple times.
    # NOTE: ADD VALUE cannot be run inside a transaction block in older PG versions.
    # Alembic runs migrations in transactions by default; these statements use
    # op.execute with autocommit-safe DDL. In PG 12+ this is fine inside a txn.
    op.execute("ALTER TYPE whatsapp_session_state ADD VALUE IF NOT EXISTS 'searching'")
    op.execute("ALTER TYPE whatsapp_session_state ADD VALUE IF NOT EXISTS 'awaiting_handle'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    # Downgrade is a no-op — the extra values cause no harm and removal is unsafe.
    pass
