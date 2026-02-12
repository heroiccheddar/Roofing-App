"""Add Redfin housing market columns to census_tracts.

Stores ZIP-level real estate market data from Redfin Data Center,
allocated to tracts via HUD USPS ZIP-to-Tract crosswalk.

Revision ID: add_redfin_columns
Revises: add_flood_hazard_columns
Create Date: 2026-02-12
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "add_redfin_columns"
down_revision: Union[str, None] = "add_flood_hazard_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("census_tracts", sa.Column("redfin_median_sale_price", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("redfin_median_dom", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("redfin_inventory", sa.Integer(), nullable=True))
    op.add_column("census_tracts", sa.Column("redfin_price_drop_pct", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("redfin_data_month", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("census_tracts", "redfin_data_month")
    op.drop_column("census_tracts", "redfin_price_drop_pct")
    op.drop_column("census_tracts", "redfin_inventory")
    op.drop_column("census_tracts", "redfin_median_dom")
    op.drop_column("census_tracts", "redfin_median_sale_price")
