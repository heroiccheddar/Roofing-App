"""Add enriched data columns for NRI, census income/occupancy, and building footprints.

Revision ID: add_enriched_data
Revises: add_lead_type
Create Date: 2026-02-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_enriched_data'
down_revision: Union[str, None] = 'add_lead_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # FEMA National Risk Index - Hail
    op.add_column('census_tracts', sa.Column('nri_hail_afreq', sa.Float(), nullable=True))
    op.add_column('census_tracts', sa.Column('nri_hail_expb', sa.Float(), nullable=True))
    op.add_column('census_tracts', sa.Column('nri_hail_ealt', sa.Float(), nullable=True))
    op.add_column('census_tracts', sa.Column('nri_hail_riskr', sa.String(), nullable=True))

    # FEMA National Risk Index - Strong Wind
    op.add_column('census_tracts', sa.Column('nri_swnd_afreq', sa.Float(), nullable=True))
    op.add_column('census_tracts', sa.Column('nri_swnd_expb', sa.Float(), nullable=True))
    op.add_column('census_tracts', sa.Column('nri_swnd_ealt', sa.Float(), nullable=True))
    op.add_column('census_tracts', sa.Column('nri_swnd_riskr', sa.String(), nullable=True))

    # FEMA National Risk Index - Tornado
    op.add_column('census_tracts', sa.Column('nri_trnd_afreq', sa.Float(), nullable=True))
    op.add_column('census_tracts', sa.Column('nri_trnd_expb', sa.Float(), nullable=True))
    op.add_column('census_tracts', sa.Column('nri_trnd_ealt', sa.Float(), nullable=True))
    op.add_column('census_tracts', sa.Column('nri_trnd_riskr', sa.String(), nullable=True))

    # Additional Census ACS Variables
    op.add_column('census_tracts', sa.Column('median_household_income', sa.Float(), nullable=True))
    op.add_column('census_tracts', sa.Column('vacancy_rate', sa.Float(), nullable=True))
    op.add_column('census_tracts', sa.Column('single_family_pct', sa.Float(), nullable=True))
    op.add_column('census_tracts', sa.Column('pct_built_before_1980', sa.Float(), nullable=True))

    # Microsoft Building Footprints (aggregated to tract)
    op.add_column('census_tracts', sa.Column('building_count', sa.Integer(), nullable=True))
    op.add_column('census_tracts', sa.Column('avg_building_area_sqm', sa.Float(), nullable=True))
    op.add_column('census_tracts', sa.Column('total_building_area_sqm', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('census_tracts', 'total_building_area_sqm')
    op.drop_column('census_tracts', 'avg_building_area_sqm')
    op.drop_column('census_tracts', 'building_count')
    op.drop_column('census_tracts', 'pct_built_before_1980')
    op.drop_column('census_tracts', 'single_family_pct')
    op.drop_column('census_tracts', 'vacancy_rate')
    op.drop_column('census_tracts', 'median_household_income')
    op.drop_column('census_tracts', 'nri_trnd_riskr')
    op.drop_column('census_tracts', 'nri_trnd_ealt')
    op.drop_column('census_tracts', 'nri_trnd_expb')
    op.drop_column('census_tracts', 'nri_trnd_afreq')
    op.drop_column('census_tracts', 'nri_swnd_riskr')
    op.drop_column('census_tracts', 'nri_swnd_ealt')
    op.drop_column('census_tracts', 'nri_swnd_expb')
    op.drop_column('census_tracts', 'nri_swnd_afreq')
    op.drop_column('census_tracts', 'nri_hail_riskr')
    op.drop_column('census_tracts', 'nri_hail_ealt')
    op.drop_column('census_tracts', 'nri_hail_expb')
    op.drop_column('census_tracts', 'nri_hail_afreq')
