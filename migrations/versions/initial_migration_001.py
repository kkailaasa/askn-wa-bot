"""Initial migration
Revision ID: 1a2b3c4d5e6f
Revises:
Create Date: 2024-11-14 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '1a2b3c4d5e6f'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Existing tables
    op.create_table(
        'conversation_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('phone_number', sa.String(length=50), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('response', sa.Text(), nullable=True),
        sa.Column('conversation_id', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_conversation_logs_conversation_id', 'conversation_logs', ['conversation_id'])
    op.create_index('ix_conversation_logs_phone_number', 'conversation_logs', ['phone_number'])

    op.create_table(
        'error_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('error_type', sa.String(length=100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('stack_trace', sa.Text(), nullable=True),
        sa.Column('conversation_id', sa.String(length=100), nullable=True),
        sa.Column('phone_number', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Load balancer tables
    op.create_table(
        'load_balancer_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_ip', sa.String(length=50), nullable=True),
        sa.Column('user_agent', sa.String(length=200), nullable=True),
        sa.Column('referrer', sa.String(length=200), nullable=True),
        sa.Column('assigned_number', sa.String(length=50), nullable=True),
        sa.Column('request_timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('additional_data', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_load_balancer_logs_assigned_number', 'load_balancer_logs', ['assigned_number'])
    op.create_index('idx_load_balancer_logs_timestamp', 'load_balancer_logs', ['request_timestamp'])

    op.create_table(
        'number_load_stats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('phone_number', sa.String(length=50), nullable=True),
        sa.Column('messages_per_second', sa.Float(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_number_load_stats_phone_timestamp', 'number_load_stats', ['phone_number', 'timestamp'])

def downgrade() -> None:
    op.drop_table('number_load_stats')
    op.drop_table('load_balancer_logs')
    op.drop_table('error_logs')
    op.drop_table('conversation_logs')