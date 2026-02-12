"""Add CDC SVI columns to census_tracts.

Stores Social Vulnerability Index data from CDC/ATSDR for
disaster vulnerability assessment and lead scoring.

Revision ID: add_svi_columns
Revises: add_percentile_ranks
Create Date: 2026-02-11
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "add_svi_columns"
down_revision: Union[str, None] = "add_percentile_ranks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("census_tracts", sa.Column("svi_overall", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("svi_socioeconomic", sa.Float(), nullable=True))
    op.add_column("census_tracts", sa.Column("svi_housing_type", sa.Float(), nullable=True))

def downgrade() -> None:
    op.drop_column("census_tracts", "svi_housing_type")
    op.drop_column("census_tracts", "svi_socioeconomic")
    op.drop_column("census_tracts", "svi_overall")
