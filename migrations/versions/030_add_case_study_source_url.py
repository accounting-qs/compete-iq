"""030_add_case_study_source_url

Add source_url column to case_studies for URL-based importer (and re-import / dedupe).

Revision ID: 030
Revises: 029
"""
from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("case_studies", sa.Column("source_url", sa.String(), nullable=True))
    op.create_index("ix_case_studies_source_url", "case_studies", ["source_url"])


def downgrade() -> None:
    op.drop_index("ix_case_studies_source_url", table_name="case_studies")
    op.drop_column("case_studies", "source_url")
