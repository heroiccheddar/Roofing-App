"""Lead zone endpoints.

Retrieves scored lead zones filtered by location, score threshold, and date range.
Supports map viewport queries and list views.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping

from app.api.deps import get_current_user
from app.database import get_db
from app.models.lead_zone import LeadZone
from app.models.roofer_account import RooferAccount
from app.models.census_tract import CensusTract
from app.models.storm_event import StormEvent
from app.schemas.zones import (
    ZoneListParams,
    ZoneResponse,
    ZoneDetailResponse,
    ZoneListResponse,
    ZoneGeoJSONResponse,
    ZoneGeoJSONFeature,
    GeoJSONGeometry,
    StormEventBrief,
    ScoreFactor,
    TractGeoJSONResponse,
)
from app.scoring.decay import calculate_decay

FEATURE_LABELS = {
    "roof_age": "Roof Age",
    "pre1980_housing": "Pre-1980 Housing",
    "owner_occupied": "Owner Occupancy",
    "home_value": "Home Value",
    "income": "Household Income",
    "low_cost_burden": "Low Cost Burden",
    "density": "Housing Density",
    "single_family": "Single Family",
    "climate_weathering": "Climate Weathering",
    "canopy_risk": "Tree Canopy Risk",
    "fema_risk": "FEMA Disaster Risk",
    "age_clustering": "Age Clustering",
    "hpi_appreciation": "Home Price Growth",
    "svi_vulnerability": "Social Vulnerability",
    "market_activity": "Market Activity",
    "low_vacancy": "Low Vacancy",
    "hail_exposure": "Hail Exposure",
    "verified_damage": "Verified Damage",
}

# Unified weights derived from the v9+ four-pillar model.
# Formula: pillar_weight * feature_weight_within_pillar
# Pillar weights: roof_condition=0.35, market_quality=0.30,
#                risk_exposure=0.20, canvass_efficiency=0.15
UNIFIED_WEIGHTS = {
    "roof_age":          0.35 * 0.35,  # roof_condition pillar
    "climate_weathering": 0.35 * 0.20 + 0.20 * 0.15,  # roof + risk pillars
    "pre1980_housing":   0.35 * 0.15,  # roof_condition pillar
    "age_clustering":    0.35 * 0.10,  # roof_condition pillar
    "canopy_risk":       0.35 * 0.10 + 0.20 * 0.15,   # roof + risk pillars
    "svi_vulnerability": 0.35 * 0.10 + 0.20 * 0.10,   # roof + risk pillars
    "owner_occupied":    0.30 * 0.20,  # market_quality pillar
    "home_value":        0.30 * 0.15,  # market_quality pillar
    "income":            0.30 * 0.18,  # market_quality pillar
    "single_family":     0.30 * 0.08 + 0.15 * 0.25,   # market + canvass pillars
    "low_vacancy":       0.30 * 0.08,  # market_quality pillar
    "low_cost_burden":   0.30 * 0.10,  # market_quality pillar
    "hpi_appreciation":  0.30 * 0.10,  # market_quality pillar
    "market_activity":   0.30 * 0.11 + 0.15 * 0.15,   # market + canvass pillars
    "fema_risk":         0.20 * 0.20,  # risk_exposure pillar
    "hail_exposure":     0.20 * 0.20,  # risk_exposure pillar
    "verified_damage":   0.20 * 0.20,  # risk_exposure pillar
    "density":           0.15 * 0.60,  # canvass_efficiency pillar
}


def compute_score_factors(
    tracts: list[CensusTract], lead_type: str
) -> list[ScoreFactor]:
    """Compute ranked score factor breakdown from census tract percentile ranks.

    Uses UNIFIED_WEIGHTS for all zones regardless of lead_type — the v9+ model
    applies the same four-pillar formula to both standard and storm-boosted zones.
    Storm boost is additive on top of base_score and is not reflected here.
    """
    total_area = sum(t.area_sq_km or 0 for t in tracts)
    if total_area == 0:
        return []

    pctile_accum: dict[str, float] = {}
    for tract in tracts:
        if not tract.area_sq_km or not tract.percentile_ranks:
            continue
        w = tract.area_sq_km / total_area
        for key, val in tract.percentile_ranks.items():
            pctile_accum[key] = pctile_accum.get(key, 0.0) + val * w

    factors = []
    for feature, weight in UNIFIED_WEIGHTS.items():
        pctile = pctile_accum.get(feature, 50.0)
        contribution = pctile * weight
        factors.append(ScoreFactor(
            name=feature,
            label=FEATURE_LABELS.get(feature, feature.replace("_", " ").title()),
            percentile=round(pctile, 1),
            weight=weight,
            contribution=round(contribution, 1),
        ))

    factors.sort(key=lambda f: f.contribution, reverse=True)
    return factors[:5]


router = APIRouter(prefix="/zones", tags=["lead-zones"])


@router.get("/geojson", response_model=ZoneGeoJSONResponse)
async def get_zones_geojson(
    min_score: float | None = None,
    lead_type: str | None = None,
    bbox: str | None = None,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return active zones as GeoJSON FeatureCollection for map rendering.

    Args:
        min_score: Optional minimum composite score filter
        lead_type: Optional filter. Accepts 'standard', 'storm_boosted',
                   and legacy values 'storm' and 'roof_age'.
        bbox: Optional viewport bounding box as 'west,south,east,north'
        current_user: Authenticated roofer account
        db: Database session

    Returns:
        GeoJSON FeatureCollection with zone polygons and properties
    """
    # Build query for active zones
    stmt = select(LeadZone).where(LeadZone.active == True)

    # Apply bbox viewport filter if provided, otherwise fall back to service area
    if bbox:
        try:
            west, south, east, north = [float(x) for x in bbox.split(",")]
            bbox_wkt = (
                f"POLYGON(({west} {south},{east} {south},"
                f"{east} {north},{west} {north},{west} {south}))"
            )
            from geoalchemy2 import WKTElement
            bbox_geom = WKTElement(bbox_wkt, srid=4326)
            stmt = stmt.where(func.ST_Intersects(LeadZone.boundary, bbox_geom))
        except (ValueError, IndexError):
            # Malformed bbox — fall back to service area
            stmt = stmt.where(
                func.ST_Intersects(LeadZone.boundary, current_user.service_area),
            )
    else:
        stmt = stmt.where(
            func.ST_Intersects(LeadZone.boundary, current_user.service_area),
        )

    # Apply optional min_score filter
    if min_score is not None:
        stmt = stmt.where(LeadZone.composite_score >= min_score)

    # Apply optional lead_type filter with legacy value mapping
    if lead_type == 'storm' or lead_type == 'storm_boosted':
        stmt = stmt.where(LeadZone.has_active_storm == True)
    elif lead_type == 'roof_age' or lead_type == 'standard':
        stmt = stmt.where(LeadZone.has_active_storm == False)
    elif lead_type is not None:
        stmt = stmt.where(LeadZone.lead_type == lead_type)

    # Cap results to prevent OOM on wide viewports — return top zones by score
    stmt = stmt.order_by(LeadZone.composite_score.desc()).limit(5000)

    # Execute query
    result = await db.execute(stmt)
    zones = result.scalars().all()

    # Convert zones to GeoJSON features
    features = []
    for zone in zones:
        # Convert PostGIS geometry to GeoJSON
        boundary_shape = to_shape(zone.boundary)
        geom = mapping(boundary_shape)

        # Create feature with zone properties
        feature = ZoneGeoJSONFeature(
            type="Feature",
            geometry=GeoJSONGeometry(
                type=geom["type"],
                coordinates=geom["coordinates"],
            ),
            properties={
                "id": str(zone.id),
                "h3_index": zone.h3_index,
                "composite_score": zone.composite_score,
                "score_band": zone.score_band,
                "max_hail_diameter": zone.max_hail_diameter,
                "max_wind_speed": zone.max_wind_speed,
                "event_count": zone.event_count,
                "lead_type": zone.lead_type,
                "display_name": zone.display_name,
                # v9+ fields (guarded for migration safety)
                "has_active_storm": getattr(zone, 'has_active_storm', False),
                "storm_boost": getattr(zone, 'storm_boost', None),
                "base_score": getattr(zone, 'base_score', None),
                "roof_condition": getattr(zone, 'roof_condition', None),
                "market_quality": getattr(zone, 'market_quality', None),
                "risk_exposure": getattr(zone, 'risk_exposure', None),
                "canvass_efficiency": getattr(zone, 'canvass_efficiency', None),
            },
        )
        features.append(feature)

    return ZoneGeoJSONResponse(
        type="FeatureCollection",
        features=features,
    )


@router.get("", response_model=ZoneListResponse)
async def list_zones(
    params: ZoneListParams = Depends(),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List active lead zones with filtering and pagination.

    Args:
        params: Query parameters (min_score, hail_min, lead_type, sort_by, page, page_size)
        current_user: Authenticated roofer account
        db: Database session

    Returns:
        Paginated list of zones with total count
    """
    # Build base query for active zones in user's service area
    stmt = select(LeadZone).where(
        LeadZone.active == True,
        func.ST_Intersects(LeadZone.boundary, current_user.service_area),
    )

    # Apply optional filters
    if params.min_score is not None:
        stmt = stmt.where(LeadZone.composite_score >= params.min_score)

    if params.hail_min is not None:
        stmt = stmt.where(LeadZone.max_hail_diameter >= params.hail_min)

    # Map old lead_type filter values to the new has_active_storm column
    if params.lead_type == 'storm' or params.lead_type == 'storm_boosted':
        stmt = stmt.where(LeadZone.has_active_storm == True)
    elif params.lead_type == 'roof_age' or params.lead_type == 'standard':
        stmt = stmt.where(LeadZone.has_active_storm == False)
    elif params.lead_type is not None:
        stmt = stmt.where(LeadZone.lead_type == params.lead_type)

    # Apply sorting
    if params.sort_by == "score":
        stmt = stmt.order_by(LeadZone.composite_score.desc())
    elif params.sort_by == "time":
        stmt = stmt.order_by(LeadZone.primary_event_timestamp.desc())
    elif params.sort_by == "hail":
        stmt = stmt.order_by(LeadZone.max_hail_diameter.desc())

    # Count total matching zones before pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Apply pagination
    offset = (params.page - 1) * params.page_size
    stmt = stmt.offset(offset).limit(params.page_size)

    # Execute query
    result = await db.execute(stmt)
    zones = result.scalars().all()

    # Convert zones to response schema
    zone_responses = []
    for zone in zones:
        # Extract centroid coordinates from PostGIS POINT
        centroid_shape = to_shape(zone.centroid)
        centroid_lat = centroid_shape.y
        centroid_lon = centroid_shape.x

        # Map zone to response schema
        zone_response = ZoneResponse(
            id=zone.id,
            h3_index=zone.h3_index,
            lead_type=zone.lead_type,
            composite_score=zone.composite_score,
            damage_prob=zone.damage_prob,
            lead_quality=zone.lead_quality,
            density_bonus=zone.density_bonus,
            predicted_conversion_rate=zone.predicted_conversion_rate,
            score_band=zone.score_band,
            model_version=zone.model_version,
            event_count=zone.event_count,
            max_hail_diameter=zone.max_hail_diameter,
            max_wind_speed=zone.max_wind_speed,
            primary_event_timestamp=zone.primary_event_timestamp,
            expires_at=zone.expires_at,
            centroid_lat=centroid_lat,
            centroid_lon=centroid_lon,
            display_name=zone.display_name,
            created_at=zone.created_at,
        )
        zone_responses.append(zone_response)

    return ZoneListResponse(
        zones=zone_responses,
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{zone_id}", response_model=ZoneDetailResponse)
async def get_zone(
    zone_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information for a specific lead zone.

    Args:
        zone_id: Zone UUID
        current_user: Authenticated roofer account
        db: Database session

    Returns:
        Zone detail with decay-adjusted score and contributing events

    Raises:
        404: Zone not found
        403: Zone outside user's service area
    """
    # Query zone by ID
    stmt = select(LeadZone).where(LeadZone.id == zone_id)
    result = await db.execute(stmt)
    zone = result.scalar_one_or_none()

    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")

    # Verify zone is within user's service area
    intersects_stmt = select(
        func.ST_Intersects(LeadZone.boundary, current_user.service_area)
    ).where(LeadZone.id == zone_id)
    intersects_result = await db.execute(intersects_stmt)
    intersects = intersects_result.scalar_one()

    if not intersects:
        raise HTTPException(
            status_code=403,
            detail="Zone is outside your service area"
        )

    # Extract centroid coordinates
    centroid_shape = to_shape(zone.centroid)
    centroid_lat = centroid_shape.y
    centroid_lon = centroid_shape.x

    # Recalculate decay-adjusted score from raw sub-scores
    raw_composite = (
        zone.damage_prob * 0.50 +
        zone.lead_quality * 0.30 +
        zone.density_bonus * 0.20
    )

    # Handle decay and hours_since for storm-boosted vs standard zones
    has_storm = getattr(zone, 'has_active_storm', False) or zone.lead_type == 'storm'
    if zone.primary_event_timestamp is None or not has_storm:
        # standard zones (no active storm) have no time decay
        decay_adjusted_score = zone.composite_score
        hours_since = 0.0
    else:
        # storm-boosted zones have decay applied
        decay_factor = calculate_decay(zone.primary_event_timestamp)
        decay_adjusted_score = max(0, min(raw_composite * decay_factor, 100))
        hours_since = (
            datetime.now(timezone.utc) - zone.primary_event_timestamp
        ).total_seconds() / 3600

    # Fetch contributing events within zone boundary only for storm-boosted zones
    event_briefs = []
    if has_storm or zone.lead_type in ('storm', 'storm_boosted'):
        events_stmt = select(StormEvent).where(
            StormEvent.scored == True,
            func.ST_Within(StormEvent.location, zone.boundary)
        ).order_by(StormEvent.event_timestamp.desc())

        events_result = await db.execute(events_stmt)
        events = events_result.scalars().all()

        # Convert events to StormEventBrief
        event_briefs = [
            StormEventBrief(
                id=event.id,
                source=event.source,
                event_type=event.event_type,
                hail_diameter=event.hail_diameter,
                wind_speed=event.wind_speed,
                event_timestamp=event.event_timestamp,
                radar_confidence=event.radar_confidence,
            )
            for event in events
        ]

    # Compute average roof age from intersecting census tracts
    avg_roof_age_years = None
    tracts_stmt = select(func.avg(CensusTract.median_year_built)).where(
        CensusTract.median_year_built.isnot(None),
        func.ST_Intersects(CensusTract.geometry, zone.boundary),
    )
    tracts_result = await db.execute(tracts_stmt)
    avg_year_built = tracts_result.scalar_one_or_none()
    if avg_year_built is not None:
        avg_roof_age_years = round(datetime.now().year - avg_year_built, 1)

    # Aggregate enriched demographics from intersecting tracts
    enriched_stmt = select(
        func.avg(CensusTract.median_household_income).label("avg_income"),
        func.avg(CensusTract.vacancy_rate).label("avg_vacancy"),
        func.avg(CensusTract.single_family_pct).label("avg_sf_pct"),
        func.avg(CensusTract.pct_built_before_1980).label("avg_pre1980"),
        func.sum(CensusTract.building_count).label("total_buildings"),
        func.avg(CensusTract.avg_building_area_sqm).label("avg_bldg_area"),
        func.avg(CensusTract.hail_exposure_score).label("avg_hail_exposure"),
        func.sum(CensusTract.hail_events_3yr).label("total_hail_events"),
        func.avg(CensusTract.fema_disaster_score).label("avg_fema_score"),
        func.max(CensusTract.fema_disaster_count).label("max_fema_count"),
        func.avg(CensusTract.tree_canopy_mean_pct).label("avg_canopy_mean"),
        func.avg(CensusTract.tree_canopy_risk_score).label("avg_canopy_risk"),
        func.avg(CensusTract.age_clustering_score).label("avg_clustering_score"),
        func.avg(CensusTract.pct_cost_burdened).label("avg_cost_burdened"),
        func.avg(CensusTract.hpi_5yr_change).label("avg_hpi_change"),
        func.avg(CensusTract.verified_damage_5yr_usd).label("avg_verified_damage"),
        func.avg(CensusTract.climate_weathering_score).label("avg_climate_weathering"),
        func.avg(CensusTract.svi_overall).label("avg_svi_overall"),
        func.avg(CensusTract.svi_housing_type).label("avg_svi_housing_type"),
        func.max(CensusTract.bps_single_family_permits).label("bps_sf_permits"),
        func.max(CensusTract.bps_all_permits).label("bps_all_permits"),
        func.max(CensusTract.bps_total_value).label("bps_total_value"),
        func.avg(CensusTract.ej_lead_paint).label("avg_ej_lead_paint"),
        func.avg(CensusTract.ej_percentile).label("avg_ej_percentile"),
        func.avg(CensusTract.redfin_median_sale_price).label("avg_redfin_sale_price"),
        func.avg(CensusTract.redfin_median_dom).label("avg_redfin_dom"),
        func.avg(CensusTract.redfin_price_drop_pct).label("avg_redfin_price_drops"),
    ).where(
        func.ST_Intersects(CensusTract.geometry, zone.boundary),
    )
    enriched_result = await db.execute(enriched_stmt)
    enriched = enriched_result.one_or_none()

    # Get the most common dominant_decade in the zone
    mode_decade_stmt = select(CensusTract.dominant_decade).where(
        func.ST_Intersects(CensusTract.geometry, zone.boundary),
        CensusTract.dominant_decade.isnot(None),
    ).group_by(CensusTract.dominant_decade).order_by(
        func.count().desc()
    ).limit(1)
    mode_decade_result = await db.execute(mode_decade_stmt)
    zone_dominant_decade = mode_decade_result.scalar_one_or_none()

    # Get most common RUCA category (mode) from intersecting tracts
    mode_ruca_stmt = select(CensusTract.ruca_category).where(
        func.ST_Intersects(CensusTract.geometry, zone.boundary),
        CensusTract.ruca_category.isnot(None),
    ).group_by(CensusTract.ruca_category).order_by(
        func.count().desc()
    ).limit(1)
    mode_ruca_result = await db.execute(mode_ruca_stmt)
    zone_ruca_category = mode_ruca_result.scalar_one_or_none()

    # Get most common flood risk category (mode) from intersecting tracts
    mode_flood_stmt = select(
        CensusTract.flood_risk_category,
        CensusTract.flood_insurance_required,
    ).where(
        func.ST_Intersects(CensusTract.geometry, zone.boundary),
        CensusTract.flood_risk_category.isnot(None),
    ).group_by(
        CensusTract.flood_risk_category,
        CensusTract.flood_insurance_required,
    ).order_by(
        func.count().desc()
    ).limit(1)
    mode_flood_result = await db.execute(mode_flood_stmt)
    flood_row = mode_flood_result.one_or_none()

    # Get most common NRI risk ratings (mode) from intersecting tracts
    # Use a simpler approach: get the first non-null value
    nri_stmt = select(
        CensusTract.nri_hail_riskr,
        CensusTract.nri_swnd_riskr,
        CensusTract.nri_trnd_riskr,
    ).where(
        func.ST_Intersects(CensusTract.geometry, zone.boundary),
        CensusTract.nri_hail_riskr.isnot(None),
    ).limit(1)
    nri_result = await db.execute(nri_stmt)
    nri_row = nri_result.one_or_none()

    # Compute score factors from census tract percentile ranks using UNIFIED_WEIGHTS
    factor_stmt = select(CensusTract).where(
        func.ST_Intersects(CensusTract.geometry, zone.boundary),
    )
    factor_result = await db.execute(factor_stmt)
    factor_tracts = list(factor_result.scalars().all())
    score_factors = compute_score_factors(factor_tracts, zone.lead_type)

    # Build detail response
    return ZoneDetailResponse(
        id=zone.id,
        h3_index=zone.h3_index,
        lead_type=zone.lead_type,
        composite_score=zone.composite_score,
        damage_prob=zone.damage_prob,
        lead_quality=zone.lead_quality,
        density_bonus=zone.density_bonus,
        predicted_conversion_rate=zone.predicted_conversion_rate,
        score_band=zone.score_band,
        model_version=zone.model_version,
        event_count=zone.event_count,
        max_hail_diameter=zone.max_hail_diameter,
        max_wind_speed=zone.max_wind_speed,
        primary_event_timestamp=zone.primary_event_timestamp,
        expires_at=zone.expires_at,
        centroid_lat=centroid_lat,
        centroid_lon=centroid_lon,
        display_name=zone.display_name,
        created_at=zone.created_at,
        decay_adjusted_score=decay_adjusted_score,
        hours_since_storm=hours_since,
        events=event_briefs,
        avg_roof_age_years=avg_roof_age_years,
        avg_median_income=enriched.avg_income if enriched else None,
        avg_vacancy_rate=enriched.avg_vacancy if enriched else None,
        avg_single_family_pct=enriched.avg_sf_pct if enriched else None,
        avg_pct_built_before_1980=enriched.avg_pre1980 if enriched else None,
        nri_hail_risk=nri_row.nri_hail_riskr if nri_row else None,
        nri_wind_risk=nri_row.nri_swnd_riskr if nri_row else None,
        nri_tornado_risk=nri_row.nri_trnd_riskr if nri_row else None,
        total_building_count=int(enriched.total_buildings) if enriched and enriched.total_buildings else None,
        avg_building_area_sqm=enriched.avg_bldg_area if enriched else None,
        hail_exposure_score=round(enriched.avg_hail_exposure, 1) if enriched and enriched.avg_hail_exposure else None,
        hail_events_3yr=int(enriched.total_hail_events) if enriched and enriched.total_hail_events else None,
        fema_disaster_count=int(enriched.max_fema_count) if enriched and enriched.max_fema_count else None,
        fema_disaster_score=round(enriched.avg_fema_score, 1) if enriched and enriched.avg_fema_score else None,
        tree_canopy_mean_pct=round(enriched.avg_canopy_mean, 1) if enriched and enriched.avg_canopy_mean else None,
        tree_canopy_risk_score=round(enriched.avg_canopy_risk, 1) if enriched and enriched.avg_canopy_risk else None,
        dominant_decade=zone_dominant_decade,
        age_clustering_score=round(enriched.avg_clustering_score, 1) if enriched and enriched.avg_clustering_score else None,
        pct_cost_burdened=round(enriched.avg_cost_burdened, 1) if enriched and enriched.avg_cost_burdened else None,
        hpi_5yr_change=round(enriched.avg_hpi_change, 1) if enriched and enriched.avg_hpi_change else None,
        verified_damage_5yr_usd=round(enriched.avg_verified_damage, 0) if enriched and enriched.avg_verified_damage else None,
        climate_weathering_score=round(enriched.avg_climate_weathering, 1) if enriched and enriched.avg_climate_weathering else None,
        svi_overall=round(enriched.avg_svi_overall, 3) if enriched and enriched.avg_svi_overall else None,
        svi_housing_type=round(enriched.avg_svi_housing_type, 3) if enriched and enriched.avg_svi_housing_type else None,
        ruca_category=zone_ruca_category,
        bps_single_family_permits=int(enriched.bps_sf_permits) if enriched and enriched.bps_sf_permits else None,
        bps_all_permits=int(enriched.bps_all_permits) if enriched and enriched.bps_all_permits else None,
        bps_total_value=enriched.bps_total_value if enriched and enriched.bps_total_value else None,
        ej_lead_paint=round(enriched.avg_ej_lead_paint, 1) if enriched and enriched.avg_ej_lead_paint else None,
        ej_percentile=round(enriched.avg_ej_percentile, 1) if enriched and enriched.avg_ej_percentile else None,
        flood_risk_category=flood_row[0] if flood_row else None,
        flood_insurance_required=flood_row[1] if flood_row else None,
        redfin_median_sale_price=round(enriched.avg_redfin_sale_price, 0) if enriched and enriched.avg_redfin_sale_price else None,
        redfin_median_dom=round(enriched.avg_redfin_dom, 1) if enriched and enriched.avg_redfin_dom else None,
        redfin_price_drop_pct=round(enriched.avg_redfin_price_drops, 1) if enriched and enriched.avg_redfin_price_drops else None,
        score_factors=score_factors,
    )


@router.get("/{zone_id}/events", response_model=list[StormEventBrief])
async def get_zone_events(
    zone_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all storm events contributing to a specific zone.

    Args:
        zone_id: Zone UUID
        current_user: Authenticated roofer account
        db: Database session

    Returns:
        List of storm events within zone boundary

    Raises:
        404: Zone not found
        403: Zone outside user's service area
    """
    # Query zone by ID
    stmt = select(LeadZone).where(LeadZone.id == zone_id)
    result = await db.execute(stmt)
    zone = result.scalar_one_or_none()

    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")

    # Verify zone is within user's service area
    intersects_stmt = select(
        func.ST_Intersects(LeadZone.boundary, current_user.service_area)
    ).where(LeadZone.id == zone_id)
    intersects_result = await db.execute(intersects_stmt)
    intersects = intersects_result.scalar_one()

    if not intersects:
        raise HTTPException(
            status_code=403,
            detail="Zone is outside your service area"
        )

    # Return empty list for standard (non-storm) zones
    has_storm = getattr(zone, 'has_active_storm', False) or zone.lead_type in ('storm', 'storm_boosted')
    if not has_storm and zone.lead_type not in ('storm', 'storm_boosted'):
        return []

    # Fetch events within zone boundary
    events_stmt = select(StormEvent).where(
        func.ST_Within(StormEvent.location, zone.boundary)
    ).order_by(StormEvent.event_timestamp.desc())

    events_result = await db.execute(events_stmt)
    events = events_result.scalars().all()

    # Convert to StormEventBrief
    return [
        StormEventBrief(
            id=event.id,
            source=event.source,
            event_type=event.event_type,
            hail_diameter=event.hail_diameter,
            wind_speed=event.wind_speed,
            event_timestamp=event.event_timestamp,
            radar_confidence=event.radar_confidence,
        )
        for event in events
    ]


def compute_canvass_priority(tract: CensusTract) -> float:
    """Compute canvass priority score (0-100) for a census tract.

    Weighted formula:
    - 30% owner_occupied_pct (homeowners authorize roof work)
    - 25% pct_built_before_1980 (older roofs need replacement)
    - 25% single_family_pct (individual roof decisions)
    - 20% median_home_value normalized to 0-100 ($50k-$500k range)
    """
    owner = tract.owner_occupied_pct or 50.0
    pre1980 = tract.pct_built_before_1980 or 50.0
    sf = tract.single_family_pct or 50.0

    # Normalize home value to 0-100 ($50k = 0, $500k = 100)
    hv = tract.median_home_value or 200000
    hv_norm = max(0, min(100, (hv - 50000) / (500000 - 50000) * 100))

    priority = owner * 0.30 + pre1980 * 0.25 + sf * 0.25 + hv_norm * 0.20
    return round(max(0, min(100, priority)), 1)


@router.get("/{zone_id}/tracts", response_model=TractGeoJSONResponse)
async def get_zone_tracts(
    zone_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get census tracts intersecting a zone as GeoJSON with canvass priority.

    Returns a FeatureCollection of tract polygons with demographic properties
    and a computed canvass_priority score for street-level targeting.
    """
    # Verify zone exists
    stmt = select(LeadZone).where(LeadZone.id == zone_id)
    result = await db.execute(stmt)
    zone = result.scalar_one_or_none()

    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")

    # Verify zone is within user's service area
    intersects_stmt = select(
        func.ST_Intersects(LeadZone.boundary, current_user.service_area)
    ).where(LeadZone.id == zone_id)
    intersects_result = await db.execute(intersects_stmt)
    if not intersects_result.scalar_one():
        raise HTTPException(status_code=403, detail="Zone is outside your service area")

    # Get intersecting census tracts
    tracts_stmt = select(CensusTract).where(
        func.ST_Intersects(CensusTract.geometry, zone.boundary),
    )
    tracts_result = await db.execute(tracts_stmt)
    tracts = tracts_result.scalars().all()

    # Convert to GeoJSON features
    features = []
    for tract in tracts:
        geom = mapping(to_shape(tract.geometry))
        priority = compute_canvass_priority(tract)

        feature = ZoneGeoJSONFeature(
            type="Feature",
            geometry=GeoJSONGeometry(
                type=geom["type"],
                coordinates=geom["coordinates"],
            ),
            properties={
                "geoid": tract.geoid,
                "canvass_priority": priority,
                "owner_occupied_pct": round(tract.owner_occupied_pct, 1) if tract.owner_occupied_pct else None,
                "single_family_pct": round(tract.single_family_pct, 1) if tract.single_family_pct else None,
                "pct_built_before_1980": round(tract.pct_built_before_1980, 1) if tract.pct_built_before_1980 else None,
                "median_home_value": tract.median_home_value,
                "median_year_built": tract.median_year_built,
                "building_count": tract.building_count,
                "dominant_decade": tract.dominant_decade,
            },
        )
        features.append(feature)

    return TractGeoJSONResponse(
        type="FeatureCollection",
        features=features,
    )
