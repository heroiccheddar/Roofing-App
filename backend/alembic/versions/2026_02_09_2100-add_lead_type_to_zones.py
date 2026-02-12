"""add_lead_type_to_lead_zones

Revision ID: add_lead_type
Revises: c7d92b5ede19
Create Date: 2026-02-09 21:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_lead_type'
down_revision: Union[str, None] = 'c7d92b5ede19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add lead_type column with default 'storm' for existing rows
    op.add_column(
        'lead_zones',
        sa.Column('lead_type', sa.String(), nullable=False, server_default='storm')
    )
    # Add index for filtering by lead_type
    op.create_index('ix_lead_zones_lead_type', 'lead_zones', ['lead_type'])
    # Composite index for lead_type + active + score queries
    op.create_index(
        'ix_lead_zones_type_active_score',
        'lead_zones',
        ['lead_type', 'active', 'composite_score'],
    )


def downgrade() -> None:
    op.drop_index('ix_lead_zones_type_active_score', table_name='lead_zones')
    op.drop_index('ix_lead_zones_lead_type', table_name='lead_zones')
    op.drop_column('lead_zones', 'lead_type')
