"""Compute and store percentile ranks for census tract features."""
import os
os.environ.setdefault("DISABLE_SQLALCHEMY_CEXT_RUNTIME", "1")

from typing import Dict, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.database import engine, AsyncSessionLocal
from app.models.census_tract import CensusTract


def compute_percentile_ranks(values: List[Tuple[str, float]], invert: bool = False) -> Dict[str, float]:
    """Compute percentile ranks for a list of (geoid, value) pairs.

    Args:
        values: List of (geoid, value) tuples
        invert: If True, invert ranks so lower values get higher percentiles

    Returns:
        Dictionary mapping geoid to percentile (0-100 scale)
    """
    if not values:
        return {}

    sorted_items = sorted(values, key=lambda x: x[1])
    n = len(sorted_items)
    ranks = {}

    for i, (geoid, _) in enumerate(sorted_items):
        pct = (i / max(n - 1, 1)) * 100
        ranks[geoid] = round(100 - pct, 1) if invert else round(pct, 1)

    return ranks


async def compute_and_store_percentiles(session: AsyncSession, state_fips: str) -> dict:
    """Compute percentile ranks for census tracts within a state.

    Args:
        session: SQLAlchemy async session
        state_fips: Two-digit state FIPS code

    Returns:
        Dictionary with statistics about the operation
    """
    # Define feature configurations: (field_name, db_column, invert)
    feature_configs = [
        ('owner_occupied', 'owner_occupied_pct', False),
        ('home_value', 'median_home_value', False),
        ('roof_age', 'median_year_built', True),  # Inverted: older (lower year) = better
        ('income', 'median_household_income', False),
        ('single_family', 'single_family_pct', False),
        ('low_vacancy', 'vacancy_rate', True),  # Inverted: lower = better
        ('low_cost_burden', 'pct_cost_burdened', True),  # Inverted: lower = better
        ('hpi_appreciation', 'hpi_5yr_change', False),
        ('verified_damage', 'verified_damage_5yr_usd', False),
        ('climate_weathering', 'climate_weathering_score', False),
        ('fema_risk', 'fema_disaster_score', False),
        ('canopy_risk', 'tree_canopy_risk_score', False),
        ('age_clustering', 'age_clustering_score', False),
        ('pre1980_housing', 'pct_built_before_1980', False),
        ('svi_vulnerability', 'svi_overall', False),  # Higher SVI = more disaster-vulnerable
        ('market_activity', 'redfin_median_dom', True),  # Inverted: lower DOM = hotter market = better
        ('hail_exposure', 'hail_exposure_score', False),
    ]

    print(f"Loading census tracts for state {state_fips}...")

    # Query all tracts for the state
    stmt = select(CensusTract).where(CensusTract.state_fips == state_fips)
    result = await session.execute(stmt)
    tracts = result.scalars().all()

    if not tracts:
        return {
            'state_fips': state_fips,
            'tracts_processed': 0,
            'error': 'No tracts found for state'
        }

    print(f"Found {len(tracts)} tracts")

    # Build a mapping of geoid -> tract object
    tract_map = {tract.geoid: tract for tract in tracts}

    # Compute percentiles for each feature
    all_percentiles = {}  # geoid -> {feature: percentile}

    for feature_name, db_column, invert in feature_configs:
        print(f"Computing percentile ranks for {feature_name}...")

        # Collect non-null values
        values = []
        for tract in tracts:
            value = getattr(tract, db_column, None)

            # Special handling for density (computed field)
            if feature_name == 'density':
                if tract.housing_units is not None and tract.area_sq_km is not None and tract.area_sq_km > 0:
                    value = tract.housing_units / tract.area_sq_km
                else:
                    value = None

            if value is not None:
                values.append((tract.geoid, float(value)))

        # Compute ranks
        if values:
            ranks = compute_percentile_ranks(values, invert=invert)

            # Store in all_percentiles dict
            for geoid, rank in ranks.items():
                if geoid not in all_percentiles:
                    all_percentiles[geoid] = {}
                all_percentiles[geoid][feature_name] = rank

        print(f"  Computed ranks for {len(values)} tracts (skipped {len(tracts) - len(values)} with NULL)")

    # Add density percentile
    print("Computing percentile ranks for density...")
    density_values = []
    for tract in tracts:
        if tract.housing_units is not None and tract.area_sq_km is not None and tract.area_sq_km > 0:
            density = tract.housing_units / tract.area_sq_km
            density_values.append((tract.geoid, density))

    if density_values:
        density_ranks = compute_percentile_ranks(density_values, invert=False)
        for geoid, rank in density_ranks.items():
            if geoid not in all_percentiles:
                all_percentiles[geoid] = {}
            all_percentiles[geoid]['density'] = rank
        print(f"  Computed density ranks for {len(density_values)} tracts")

    # Fill in defaults (50.0) for missing values
    all_feature_names = [fc[0] for fc in feature_configs] + ['density']
    for geoid in tract_map.keys():
        if geoid not in all_percentiles:
            all_percentiles[geoid] = {}
        for feature_name in all_feature_names:
            if feature_name not in all_percentiles[geoid]:
                all_percentiles[geoid][feature_name] = 50.0

    # Batch update the percentile_ranks column
    print("Updating database in batches...")
    batch_size = 500
    updated_count = 0

    geoids = list(all_percentiles.keys())
    for i in range(0, len(geoids), batch_size):
        batch_geoids = geoids[i:i + batch_size]

        # Prepare batch updates
        for geoid in batch_geoids:
            percentiles = all_percentiles[geoid]
            stmt = (
                update(CensusTract)
                .where(CensusTract.geoid == geoid)
                .values(percentile_ranks=percentiles)
            )
            await session.execute(stmt)

        await session.commit()
        updated_count += len(batch_geoids)
        print(f"  Updated {updated_count}/{len(geoids)} tracts")

    print("Percentile computation complete!")

    return {
        'state_fips': state_fips,
        'tracts_processed': len(all_percentiles),
        'features_computed': len(all_feature_names),
        'batches': (len(geoids) + batch_size - 1) // batch_size
    }
