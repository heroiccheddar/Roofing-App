"""Add neighborhood_name column to census_tracts.

Revision ID: add_neighborhood_name
Revises: add_properties_001
Create Date: 2026-02-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "add_neighborhood_name"
down_revision: Union[str, None] = "add_properties_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "census_tracts",
        sa.Column("neighborhood_name", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("census_tracts", "neighborhood_name")
