"""032_add_case_study_structured

Add `structured` JSONB column to `case_studies` to hold the rich extracted
representation (verbatim quote, before/after metrics, pain points,
outcomes, persona) so the copy generator can use clean signal instead of
re-parsing the narrative `content` blob.

Revision ID: 032
Revises: 031
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "case_studies",
        sa.Column("structured", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("case_studies", "structured")
