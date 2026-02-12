"""Add EPA EJSCREEN columns to census_tracts.

Stores tract-level environmental justice indicators from EPA EJSCREEN.

Revision ID: add_ejscreen_columns
Revises: add_building_permit_columns
Create Date: 2026-02-11
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "add_ejscreen_columns"
down_revision: Union[str, None] = "add_building_permit_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("census_tracts", sa.Column("ej_pm25", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("ej_lead_paint", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("ej_superfund_proximity", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("ej_wastewater", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("ej_percentile", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("census_tracts", "ej_percentile")
    op.drop_column("census_tracts", "ej_wastewater")
    op.drop_column("census_tracts", "ej_superfund_proximity")
    op.drop_column("census_tracts", "ej_lead_paint")
    op.drop_column("census_tracts", "ej_pm25")
