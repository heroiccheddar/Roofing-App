"""Add Census Building Permits columns to census_tracts.

Stores county-level annual building permit data from Census Bureau BPS.
All tracts in the same county share the same values.

Revision ID: add_building_permit_columns
Revises: add_ruca_columns
Create Date: 2026-02-11
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "add_building_permit_columns"
down_revision: Union[str, None] = "add_ruca_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("census_tracts", sa.Column("bps_single_family_permits", sa.Integer(), nullable=True))
    op.add_column("census_tracts", sa.Column("bps_all_permits", sa.Integer(), nullable=True))
    op.add_column("census_tracts", sa.Column("bps_total_value", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("bps_survey_year", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("census_tracts", "bps_survey_year")
    op.drop_column("census_tracts", "bps_total_value")
    op.drop_column("census_tracts", "bps_all_permits")
    op.drop_column("census_tracts", "bps_single_family_permits")
