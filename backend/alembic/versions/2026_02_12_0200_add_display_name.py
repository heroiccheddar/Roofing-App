"""Add display_name column to lead_zones.

Stores human-readable location (e.g., 'Plano, TX') from Mapbox reverse geocoding.

Revision ID: add_display_name
Revises: add_redfin_columns
Create Date: 2026-02-12
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "add_display_name"
down_revision: Union[str, None] = "add_redfin_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lead_zones", sa.Column("display_name", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("lead_zones", "display_name")
