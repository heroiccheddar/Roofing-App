"""Add properties table for county parcel data cache.

Revision ID: add_properties_001
Revises: add_last_canvassed_at
Create Date: 2026-02-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry

revision: str = "add_properties_001"
down_revision: Union[str, None] = "add_last_canvassed_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "properties",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("county_fips", sa.String(5), nullable=False),
        sa.Column("parcel_id", sa.String(), nullable=False),
        sa.Column("source_county", sa.String(), nullable=False),
        sa.Column("tract_geoid", sa.String(), nullable=True),
        sa.Column("location", Geometry("POINT", srid=4326), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("owner_name", sa.String(), nullable=True),
        sa.Column("year_built", sa.Integer(), nullable=True),
        sa.Column("assessed_value", sa.Float(), nullable=True),
        sa.Column("land_value", sa.Float(), nullable=True),
        sa.Column("improvement_value", sa.Float(), nullable=True),
        sa.Column("square_footage", sa.Integer(), nullable=True),
        sa.Column("lot_size_sqft", sa.Float(), nullable=True),
        sa.Column("lot_size_acres", sa.Float(), nullable=True),
        sa.Column("zoning", sa.String(), nullable=True),
        sa.Column("land_use_code", sa.String(), nullable=True),
        sa.Column("property_type", sa.String(), nullable=True),
        sa.Column("bedrooms", sa.Integer(), nullable=True),
        sa.Column("bathrooms", sa.Float(), nullable=True),
        sa.Column("stories", sa.Integer(), nullable=True),
        sa.Column("last_sale_date", sa.Date(), nullable=True),
        sa.Column("last_sale_price", sa.Float(), nullable=True),
        sa.Column("estimated_roof_age", sa.Integer(), nullable=True),
        sa.Column("roof_material", sa.String(), nullable=True),
        sa.Column("raw_attributes", JSONB(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_accessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_properties_location",
        "properties",
        ["location"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_properties_county_parcel",
        "properties",
        ["source_county", "parcel_id"],
        unique=True,
    )
    op.create_index("ix_properties_tract_geoid", "properties", ["tract_geoid"])
    op.create_index("ix_properties_year_built", "properties", ["year_built"])
    op.create_index(
        "ix_properties_last_accessed_at", "properties", ["last_accessed_at"]
    )


def downgrade() -> None:
    op.drop_table("properties")
