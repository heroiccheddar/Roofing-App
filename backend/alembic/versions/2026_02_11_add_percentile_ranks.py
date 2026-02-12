"""Add percentile_ranks JSONB column to census_tracts.

Stores pre-computed percentile ranks (0-100) for all scoring features
within each state. Enables percentile-normalized scoring that spreads
zone scores across the full 0-100 range.

Revision ID: add_percentile_ranks
Revises: add_climate_financial
Create Date: 2026-02-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "add_percentile_ranks"
down_revision: Union[str, None] = "add_climate_financial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "census_tracts",
        sa.Column("percentile_ranks", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("census_tracts", "percentile_ranks")
