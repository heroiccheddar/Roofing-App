"""Add historical hail exposure and FEMA disaster declaration columns.

Revision ID: add_hail_fema
Revises: add_enriched_data
Create Date: 2026-02-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "add_hail_fema"
down_revision: Union[str, None] = "add_enriched_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Historical Hail Exposure (NOAA SWDI MESH, aggregated over 3 years)
    op.add_column("census_tracts", sa.Column("hail_events_3yr", sa.Integer(), nullable=True))
    op.add_column("census_tracts", sa.Column("max_hail_diameter_3yr", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("avg_hail_diameter_3yr", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("hail_exposure_score", sa.Float(), nullable=True))

    # FEMA Disaster Declarations (county-level, mapped to tracts)
    op.add_column("census_tracts", sa.Column("fema_disaster_count", sa.Integer(), nullable=True))
    op.add_column("census_tracts", sa.Column("fema_last_disaster_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("census_tracts", sa.Column("fema_disaster_types", JSONB(), nullable=True))
    op.add_column("census_tracts", sa.Column("fema_disaster_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("census_tracts", "fema_disaster_score")
    op.drop_column("census_tracts", "fema_disaster_types")
    op.drop_column("census_tracts", "fema_last_disaster_date")
    op.drop_column("census_tracts", "fema_disaster_count")
    op.drop_column("census_tracts", "hail_exposure_score")
    op.drop_column("census_tracts", "avg_hail_diameter_3yr")
    op.drop_column("census_tracts", "max_hail_diameter_3yr")
    op.drop_column("census_tracts", "hail_events_3yr")
