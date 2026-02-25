"""Recommendation endpoint — "Where should I go today?"

Returns the top N lead zones ranked by a composite recommendation_score
that blends zone quality (composite_score), proximity to the canvasser's
current position, zone freshness (days since last canvass), and active
storm activity.

Scoring formula
---------------
rec_score = 0.35 * composite_score
           + 0.25 * proximity
           + 0.25 * freshness
           + 0.15 * storm

    proximity = 100 * 0.98^distance_km          (exponential decay, ~50% at 34 km)
    freshness = 100 if never canvassed,
                else min(100, days_since * 100/14)   (full credit after 14 days)
    storm     = storm_boost * recency_decay if has_active_storm, else 0
                recency_decay = 0.98^hours_since_event

Zones beyond 150 km are silently excluded from recommendations because the
drive time cost exceeds any realistic lead-quality benefit.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.shape import to_shape

from app.api.deps import get_current_user
from app.database import get_db
from app.models.lead_zone import LeadZone
from app.models.roofer_account import RooferAccount
from app.schemas.recommend import RecommendedZone, RecommendationResponse
from app.utils.geo import haversine_km

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

# Recommendation weight constants
_W_SCORE = 0.35
_W_PROXIMITY = 0.25
_W_FRESHNESS = 0.25
_W_STORM = 0.15

# Geographic limits
_MAX_CANDIDATE_ZONES = 200
_MAX_DISTANCE_KM = 150.0

# Freshness: full score after this many days since last canvass
_FRESHNESS_FULL_DAYS = 14.0

# Proximity decay base per km (100 * 0.98^distance_km → ~50% at ~34 km)
_PROXIMITY_DECAY_PER_KM = 0.98

# Storm recency decay base per hour
_STORM_DECAY_PER_HOUR = 0.98


def _proximity_score(distance_km: float) -> float:
    """Exponential proximity score in [0, 100]. Decays ~50% by 34 km."""
    return 100.0 * (_PROXIMITY_DECAY_PER_KM ** distance_km)


def _freshness_score(last_canvassed_at: datetime | None, now: datetime) -> float:
    """Staleness score in [0, 100].

    Never-canvassed zones return 100. Freshly canvassed zones (< 1 day ago)
    return a small non-zero value. Zones untouched for >= 14 days return 100.
    """
    if last_canvassed_at is None:
        return 100.0
    delta_days = (now - last_canvassed_at).total_seconds() / 86400.0
    return min(100.0, delta_days * 100.0 / _FRESHNESS_FULL_DAYS)


def _storm_score(
    has_active_storm: bool,
    storm_boost: float | None,
    primary_event_timestamp: datetime | None,
    now: datetime,
) -> float:
    """Storm component in [0, 100].

    Returns 0 for zones with no active storm. For storm-boosted zones,
    applies an hourly recency decay to the raw storm_boost value so that
    the urgency of very recent events is captured.
    """
    if not has_active_storm or storm_boost is None:
        return 0.0

    recency_decay = 1.0
    if primary_event_timestamp is not None:
        hours_since = (now - primary_event_timestamp).total_seconds() / 3600.0
        recency_decay = _STORM_DECAY_PER_HOUR ** hours_since

    return storm_boost * recency_decay


def _build_reason(
    composite_score: float,
    proximity_score: float,
    freshness_score: float,
    storm_score: float,
    distance_km: float,
    has_active_storm: bool,
    last_canvassed_at: datetime | None,
) -> str:
    """Generate a concise human-readable explanation for the recommendation.

    Identifies the top two contributing factors by weighted contribution and
    builds a natural sentence from them. This gives canvassers actionable
    context without exposing raw score internals.
    """
    factors = [
        ("zone quality", _W_SCORE * composite_score, composite_score),
        ("proximity", _W_PROXIMITY * proximity_score, proximity_score),
        ("freshness", _W_FRESHNESS * freshness_score, freshness_score),
        ("storm activity", _W_STORM * storm_score, storm_score),
    ]
    # Sort descending by weighted contribution
    factors.sort(key=lambda t: t[1], reverse=True)

    top_name, _, top_raw = factors[0]
    second_name, _, _ = factors[1]

    parts = []

    # Describe top factor
    if top_name == "zone quality":
        if composite_score >= 80:
            parts.append("High-scoring zone")
        elif composite_score >= 60:
            parts.append("Good-scoring zone")
        else:
            parts.append("Moderate-scoring zone")
    elif top_name == "proximity":
        if distance_km < 5:
            parts.append(f"Very close ({distance_km:.1f} km away)")
        elif distance_km < 20:
            parts.append(f"Nearby ({distance_km:.1f} km away)")
        else:
            parts.append(f"{distance_km:.1f} km away")
    elif top_name == "freshness":
        if last_canvassed_at is None:
            parts.append("Never been canvassed")
        else:
            parts.append("Overdue for a visit")
    elif top_name == "storm activity":
        parts.append("Active storm damage reported")

    # Describe secondary factor as a qualifier
    if second_name == "proximity" and top_name != "proximity":
        if distance_km < 10:
            parts.append(f"just {distance_km:.1f} km away")
        else:
            parts.append(f"{distance_km:.1f} km from your location")
    elif second_name == "freshness" and top_name != "freshness":
        if last_canvassed_at is None:
            parts.append("never previously canvassed")
        else:
            parts.append("due for a return visit")
    elif second_name == "storm activity" and top_name != "storm activity" and has_active_storm:
        parts.append("with active storm boost")
    elif second_name == "zone quality" and top_name != "zone quality":
        if composite_score >= 75:
            parts.append(f"strong base score ({composite_score:.0f})")
        else:
            parts.append(f"base score {composite_score:.0f}")

    return " — ".join(parts) if len(parts) > 1 else parts[0] if parts else "Recommended zone"


@router.get("", response_model=RecommendationResponse)
async def get_recommendations(
    lat: float = Query(..., ge=-90, le=90, description="Canvasser's current latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Canvasser's current longitude"),
    limit: int = Query(5, ge=1, le=50, description="Number of zones to return"),
    storm_only: bool = Query(False, description="Restrict results to storm-boosted zones only"),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RecommendationResponse:
    """Return the top N recommended zones ranked for today's canvassing.

    Combines zone quality, drive proximity, canvass staleness, and storm
    urgency into a single recommendation_score. Results are filtered to the
    authenticated user's service area and zones within 150 km.

    Args:
        lat: Canvasser's current latitude (WGS84 decimal degrees)
        lon: Canvasser's current longitude (WGS84 decimal degrees)
        limit: Maximum number of zones to return (1-50, default 5)
        storm_only: When true, restrict to zones with has_active_storm=True
        current_user: Authenticated roofer account (injected)
        db: Async database session (injected)

    Returns:
        RecommendationResponse with up to `limit` scored zones and generation timestamp
    """
    now = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # 1. Fetch top 200 active zones within the user's service area,
    #    ordered by composite_score descending so we get the best candidates.
    # ------------------------------------------------------------------
    stmt = (
        select(LeadZone)
        .where(
            LeadZone.active == True,
            func.ST_Intersects(LeadZone.boundary, current_user.service_area),
        )
    )

    if storm_only:
        stmt = stmt.where(LeadZone.has_active_storm == True)

    stmt = stmt.order_by(LeadZone.composite_score.desc()).limit(_MAX_CANDIDATE_ZONES)

    result = await db.execute(stmt)
    candidate_zones = result.scalars().all()

    logger.debug(
        "Recommendation engine: %d candidate zones for user %s at (%.4f, %.4f)",
        len(candidate_zones),
        current_user.id,
        lat,
        lon,
    )

    # ------------------------------------------------------------------
    # 2. Score each candidate zone.
    # ------------------------------------------------------------------
    scored: list[tuple[float, RecommendedZone]] = []

    for zone in candidate_zones:
        # Extract centroid coordinates from PostGIS POINT geometry
        centroid_shape = to_shape(zone.centroid)
        centroid_lat = centroid_shape.y
        centroid_lon = centroid_shape.x

        # Distance gate — skip zones beyond the max useful driving radius
        distance_km = haversine_km(lat, lon, centroid_lat, centroid_lon)
        if distance_km > _MAX_DISTANCE_KM:
            continue

        # Compute sub-scores
        prox = _proximity_score(distance_km)
        fresh = _freshness_score(
            zone.last_canvassed_at,  # type: ignore[attr-defined]
            now,
        )
        storm = _storm_score(
            zone.has_active_storm,
            zone.storm_boost,
            zone.primary_event_timestamp,
            now,
        )

        rec_score = (
            _W_SCORE * zone.composite_score
            + _W_PROXIMITY * prox
            + _W_FRESHNESS * fresh
            + _W_STORM * storm
        )

        reason = _build_reason(
            composite_score=zone.composite_score,
            proximity_score=prox,
            freshness_score=fresh,
            storm_score=storm,
            distance_km=distance_km,
            has_active_storm=zone.has_active_storm,
            last_canvassed_at=zone.last_canvassed_at,  # type: ignore[attr-defined]
        )

        recommended = RecommendedZone(
            zone_id=zone.id,
            h3_index=zone.h3_index,
            display_name=zone.display_name,
            composite_score=round(zone.composite_score, 2),
            recommendation_score=round(rec_score, 2),
            distance_km=round(distance_km, 2),
            last_canvassed_at=zone.last_canvassed_at,  # type: ignore[attr-defined]
            has_active_storm=zone.has_active_storm,
            storm_boost=zone.storm_boost,
            centroid_lat=centroid_lat,
            centroid_lon=centroid_lon,
            score_band=zone.score_band,
            reason=reason,
        )
        scored.append((rec_score, recommended))

    # ------------------------------------------------------------------
    # 3. Sort by recommendation_score descending and return top N.
    # ------------------------------------------------------------------
    scored.sort(key=lambda t: t[0], reverse=True)
    top_zones = [zone for _, zone in scored[:limit]]

    logger.info(
        "Recommendation engine: returning %d zones for user %s (from %d within %d km)",
        len(top_zones),
        current_user.id,
        len(scored),
        _MAX_DISTANCE_KM,
    )

    return RecommendationResponse(zones=top_zones, generated_at=now)
