"""Add subdivision age clustering columns.

Revision ID: add_age_clustering
Revises: add_tree_canopy
Create Date: 2026-02-10 14:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "add_age_clustering"
down_revision: Union[str, None] = "add_tree_canopy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Subdivision Age Clustering (Census ACS B25034 decade distribution)
    op.add_column("census_tracts", sa.Column("dominant_decade", sa.String(), nullable=True))
    op.add_column("census_tracts", sa.Column("dominant_decade_pct", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("age_hhi", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("age_clustering_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("census_tracts", "age_clustering_score")
    op.drop_column("census_tracts", "age_hhi")
    op.drop_column("census_tracts", "dominant_decade_pct")
    op.drop_column("census_tracts", "dominant_decade")
