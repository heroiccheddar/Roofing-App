"""Environmental Justice indicator loader.

Computes EJ indicators from existing Census ACS data already in the database.
EPA EJSCREEN FTP (gaftp.epa.gov) was discontinued February 2025, so we derive
proxy indicators from Census variables we've already loaded:

- ej_lead_paint: Proxy from pct_built_before_1980 (lead paint banned 1978)
- ej_percentile: Composite vulnerability index from old housing, cost burden,
  vacancy rate, and income (0-100 percentile within state)
"""

import logging
from typing import Any

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)


async def load_ejscreen_data(
    session: AsyncSession,
    state_fips_codes: list[str],
) -> dict[str, Any]:
    """Compute EJ proxy indicators from existing Census data.

    Uses pct_built_before_1980 as lead paint proxy and builds a composite
    EJ vulnerability percentile from housing age, cost burden, vacancy, income.

    Args:
        session: SQLAlchemy async session
        state_fips_codes: List of 2-digit state FIPS codes

    Returns:
        Stats dict with tracts_queried, tracts_updated, errors
    """
    stats = {
        "tracts_queried": 0,
        "tracts_updated": 0,
        "errors": 0,
    }

    logger.info(
        f"Computing EJ indicators from Census data for states: {state_fips_codes}"
    )

    try:
        # Fetch all tracts in the target states that have housing age data
        stmt = select(
            CensusTract.geoid,
            CensusTract.pct_built_before_1980,
            CensusTract.pct_cost_burdened,
            CensusTract.vacancy_rate,
            CensusTract.median_household_income,
            CensusTract.median_home_value,
        ).where(
            CensusTract.state_fips.in_(state_fips_codes),
        )

        result = await session.execute(stmt)
        rows = result.all()
        stats["tracts_queried"] = len(rows)

        if not rows:
            logger.warning("No tracts found for the given states")
            return stats

        logger.info(f"Found {len(rows)} tracts, computing EJ indicators...")

        # Step 1: Compute raw EJ scores for each tract
        tract_scores = []
        for row in rows:
            geoid = row.geoid
            pct_old = row.pct_built_before_1980 or 0.0
            cost_burden = row.pct_cost_burdened or 0.0
            vacancy = row.vacancy_rate or 0.0
            income = row.median_household_income

            # Lead paint proxy: pre-1980 housing % (lead paint banned 1978)
            # Scale slightly — pre-1960 housing has the highest risk, but all
            # pre-1978 housing potentially contains lead paint
            ej_lead_paint = round(min(pct_old, 100.0), 1)

            # Raw vulnerability score (0-100 range each component)
            # Higher = more vulnerable / more EJ concern
            old_housing_score = min(pct_old, 100.0)  # 0-100
            cost_burden_score = min(cost_burden, 100.0)  # 0-100
            vacancy_score = min(vacancy * 2.0, 100.0)  # vacancy rates up to 50% → 100
            # Income: lower income = higher vulnerability
            # US median ~$75k; tracts range from ~$10k to $250k+
            if income and income > 0:
                income_score = max(0, min(100, (1.0 - income / 150_000) * 100))
            else:
                income_score = 50.0  # neutral if missing

            # Composite raw score (weighted average)
            raw_score = (
                old_housing_score * 0.30
                + cost_burden_score * 0.25
                + vacancy_score * 0.20
                + income_score * 0.25
            )

            tract_scores.append({
                "geoid": geoid,
                "ej_lead_paint": ej_lead_paint,
                "raw_score": raw_score,
            })

        # Step 2: Convert raw scores to percentile ranks within state
        raw_scores = sorted(t["raw_score"] for t in tract_scores)
        n = len(raw_scores)

        def percentile_rank(value: float) -> float:
            """Compute percentile rank (0-100) within the distribution."""
            # Count values below this one
            below = 0
            for s in raw_scores:
                if s < value:
                    below += 1
                else:
                    break
            return round((below / n) * 100, 1) if n > 0 else 50.0

        # Step 3: Batch update tracts
        batch_size = 500
        for i in range(0, len(tract_scores), batch_size):
            batch = tract_scores[i:i + batch_size]

            for t in batch:
                ej_percentile = percentile_rank(t["raw_score"])
                try:
                    stmt = (
                        update(CensusTract)
                        .where(CensusTract.geoid == t["geoid"])
                        .values(
                            ej_lead_paint=t["ej_lead_paint"],
                            ej_percentile=ej_percentile,
                        )
                    )
                    await session.execute(stmt)
                    stats["tracts_updated"] += 1
                except Exception as e:
                    logger.error(f"Error updating tract {t['geoid']}: {e}")
                    stats["errors"] += 1

            try:
                await session.commit()
                logger.info(
                    f"  Updated batch {i // batch_size + 1} "
                    f"({min(i + batch_size, len(tract_scores))}/{len(tract_scores)} tracts)"
                )
            except Exception as e:
                logger.error(f"Error committing batch: {e}")
                await session.rollback()
                stats["errors"] += batch_size

        logger.info(
            f"EJ indicator load complete: {stats['tracts_updated']} updated, "
            f"{stats['errors']} errors"
        )

    except Exception as e:
        logger.error(f"Error computing EJ indicators: {e}", exc_info=True)
        stats["errors"] += 1

    return stats
