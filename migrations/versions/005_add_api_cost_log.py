"""Add api_cost_log table for tracking Claude API usage and costs

Revision ID: 005
Revises: 004
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('api_cost_log',
        sa.Column('id', sa.Text(), nullable=False, server_default=sa.text("gen_random_uuid()::text")),
        sa.Column('api_name', sa.Text(), nullable=False),
        sa.Column('model', sa.Text(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(10, 6), nullable=False),
        sa.Column('session_id', sa.Text(), nullable=True),
        sa.Column('session_label', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_api_cost_log_created_at', 'api_cost_log', ['created_at'])
    op.create_index('idx_api_cost_log_api_name', 'api_cost_log', ['api_name'])


def downgrade() -> None:
    op.drop_index('idx_api_cost_log_api_name', table_name='api_cost_log')
    op.drop_index('idx_api_cost_log_created_at', table_name='api_cost_log')
    op.drop_table('api_cost_log')
