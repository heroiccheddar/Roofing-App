"""Add FEMA Flood Hazard columns to census_tracts.

Stores flood zone classification from FEMA National Flood Hazard Layer.

Revision ID: add_flood_hazard_columns
Revises: add_ejscreen_columns
Create Date: 2026-02-11
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "add_flood_hazard_columns"
down_revision: Union[str, None] = "add_ejscreen_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("census_tracts", sa.Column("flood_zone_code", sa.String(), nullable=True))
    op.add_column("census_tracts", sa.Column("flood_risk_category", sa.String(), nullable=True))
    op.add_column("census_tracts", sa.Column("flood_insurance_required", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("census_tracts", "flood_insurance_required")
    op.drop_column("census_tracts", "flood_risk_category")
    op.drop_column("census_tracts", "flood_zone_code")
