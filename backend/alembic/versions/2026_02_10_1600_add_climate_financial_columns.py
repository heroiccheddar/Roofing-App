"""Add climate and financial enrichment columns.

Revision ID: add_climate_financial
Revises: add_age_clustering
Create Date: 2026-02-10 16:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "add_climate_financial"
down_revision: Union[str, None] = "add_age_clustering"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Housing Cost Burden (Census ACS B25091)
    op.add_column("census_tracts", sa.Column("pct_cost_burdened", sa.Float(), nullable=True))

    # FHFA House Price Index
    op.add_column("census_tracts", sa.Column("hpi_5yr_change", sa.Float(), nullable=True))

    # NCEI Storm Events (Verified Damage)
    op.add_column("census_tracts", sa.Column("verified_damage_5yr_usd", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("verified_events_5yr", sa.Integer(), nullable=True))

    # NASA POWER Climate Weathering
    op.add_column("census_tracts", sa.Column("freeze_thaw_days", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("annual_solar_ghi", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("climate_weathering_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("census_tracts", "climate_weathering_score")
    op.drop_column("census_tracts", "annual_solar_ghi")
    op.drop_column("census_tracts", "freeze_thaw_days")
    op.drop_column("census_tracts", "verified_events_5yr")
    op.drop_column("census_tracts", "verified_damage_5yr_usd")
    op.drop_column("census_tracts", "hpi_5yr_change")
    op.drop_column("census_tracts", "pct_cost_burdened")
