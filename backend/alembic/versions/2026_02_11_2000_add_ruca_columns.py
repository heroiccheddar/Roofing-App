"""Add USDA RUCA code columns to census_tracts.

Stores Rural-Urban Commuting Area codes for urban/rural
classification of census tracts.

Revision ID: add_ruca_columns
Revises: add_svi_columns
Create Date: 2026-02-11
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "add_ruca_columns"
down_revision: Union[str, None] = "add_svi_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("census_tracts", sa.Column("ruca_primary", sa.Integer(), nullable=True))
    op.add_column("census_tracts", sa.Column("ruca_category", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("census_tracts", "ruca_category")
    op.drop_column("census_tracts", "ruca_primary")
