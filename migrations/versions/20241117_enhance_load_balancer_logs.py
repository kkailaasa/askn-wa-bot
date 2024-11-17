"""Add CF country and enhance load balancer logs

Revision ID: enhance_lb_logs_002
Revises: {previous_revision}
Create Date: 2024-11-17 19:15:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers
revision = 'enhance_lb_logs_002'
down_revision = '1a2b3c4d5e6f'  # Previous migration ID
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add CF country column
    op.add_column('load_balancer_logs',
        sa.Column('cf_country', sa.String(2),
            nullable=True,
            comment='Country code from CF-IPCountry header'
        )
    )

    # Add index for country code
    op.create_index(
        'idx_lb_logs_country',
        'load_balancer_logs',
        ['cf_country']
    )

    # Add composite index for analytics
    op.create_index(
        'idx_lb_logs_country_timestamp',
        'load_balancer_logs',
        ['cf_country', 'request_timestamp']
    )

def downgrade() -> None:
    # Remove indices first
    op.drop_index('idx_lb_logs_country', table_name='load_balancer_logs')
    op.drop_index('idx_lb_logs_country_timestamp', table_name='load_balancer_logs')

    # Remove the column
    op.drop_column('load_balancer_logs', 'cf_country')