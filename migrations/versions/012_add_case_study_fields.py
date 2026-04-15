"""012_add_case_study_fields

Add industry, tags, and is_active columns to case_studies table
for bucket matching during copy generation.

Revision ID: 012
Revises: 011
"""
from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("case_studies", sa.Column("industry", sa.String(), nullable=True))
    op.add_column("case_studies", sa.Column("tags", sa.JSON(), nullable=True, server_default="[]"))
    op.add_column("case_studies", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))
    op.create_index("ix_case_studies_industry", "case_studies", ["industry"])


def downgrade() -> None:
    op.drop_index("ix_case_studies_industry", table_name="case_studies")
    op.drop_column("case_studies", "is_active")
    op.drop_column("case_studies", "tags")
    op.drop_column("case_studies", "industry")
