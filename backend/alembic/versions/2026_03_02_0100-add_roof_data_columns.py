"""Add Google Solar roof geometry columns to properties table.

Stores roof measurement data fetched on-demand from the Google Solar API:
area, facet count, pitch statistics, per-facet geometry, and imagery metadata.
All columns are nullable — existing properties have no solar data until the
POST /{property_id}/roof-data endpoint is called.

Revision ID: add_roof_data_columns
Revises: add_activity_type
Create Date: 2026-03-02 01:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "add_roof_data_columns"
down_revision: Union[str, None] = "add_activity_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column("roof_area_sqft", sa.Float(), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("roof_ground_area_sqft", sa.Float(), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("roof_facet_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("roof_avg_pitch_deg", sa.Float(), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("roof_max_pitch_deg", sa.Float(), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("roof_facets", JSONB(), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("solar_imagery_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("solar_imagery_quality", sa.String(), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("solar_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("properties", "solar_fetched_at")
    op.drop_column("properties", "solar_imagery_quality")
    op.drop_column("properties", "solar_imagery_date")
    op.drop_column("properties", "roof_facets")
    op.drop_column("properties", "roof_max_pitch_deg")
    op.drop_column("properties", "roof_avg_pitch_deg")
    op.drop_column("properties", "roof_facet_count")
    op.drop_column("properties", "roof_ground_area_sqft")
    op.drop_column("properties", "roof_area_sqft")
