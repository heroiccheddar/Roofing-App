"""Add tree canopy coverage columns.

Revision ID: add_tree_canopy
Revises: add_hail_fema
Create Date: 2026-02-10 12:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "add_tree_canopy"
down_revision: Union[str, None] = "add_hail_fema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tree Canopy Coverage (USFS NLCD, aggregated from 30m raster)
    op.add_column("census_tracts", sa.Column("tree_canopy_mean_pct", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("tree_canopy_max_pct", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("tree_canopy_std_pct", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("tree_canopy_risk_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("census_tracts", "tree_canopy_risk_score")
    op.drop_column("census_tracts", "tree_canopy_std_pct")
    op.drop_column("census_tracts", "tree_canopy_max_pct")
    op.drop_column("census_tracts", "tree_canopy_mean_pct")
