"""019_add_custom_list_support

Add custom list upload mode, extend assignments and copies to support
custom lists alongside buckets.

Revision ID: 019
Revises: 018
"""
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # upload_history: track upload mode and custom list name
    op.execute("ALTER TABLE upload_history ADD COLUMN IF NOT EXISTS upload_mode VARCHAR(20) NOT NULL DEFAULT 'bucket'")
    op.execute("ALTER TABLE upload_history ADD COLUMN IF NOT EXISTS custom_list_name TEXT")

    # webinar_list_assignments: link to source upload for custom lists
    op.execute("ALTER TABLE webinar_list_assignments ADD COLUMN IF NOT EXISTS source_upload_id UUID REFERENCES upload_history(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE webinar_list_assignments ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'bucket'")

    # bucket_copies: allow copies without a bucket (for custom lists)
    op.execute("ALTER TABLE bucket_copies ALTER COLUMN bucket_id DROP NOT NULL")
    op.execute("ALTER TABLE bucket_copies ADD COLUMN IF NOT EXISTS upload_id UUID REFERENCES upload_history(id) ON DELETE CASCADE")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bucket_copies_upload_id ON bucket_copies (upload_id)")

    # Performance indexes for custom list queries
    op.execute("CREATE INDEX IF NOT EXISTS ix_wla_source_upload_id ON webinar_list_assignments (source_upload_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contacts_upload_status_bucket ON contacts (upload_id, outreach_status, bucket_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_contacts_upload_status_bucket")
    op.execute("DROP INDEX IF EXISTS ix_wla_source_upload_id")
    op.drop_index("ix_bucket_copies_upload_id", table_name="bucket_copies")
    op.drop_column("bucket_copies", "upload_id")
    op.execute("ALTER TABLE bucket_copies ALTER COLUMN bucket_id SET NOT NULL")
    op.drop_column("webinar_list_assignments", "source_type")
    op.drop_column("webinar_list_assignments", "source_upload_id")
    op.drop_column("upload_history", "custom_list_name")
    op.drop_column("upload_history", "upload_mode")
