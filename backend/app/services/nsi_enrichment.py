"""NSI (National Structures Inventory) enrichment service.

Fills in year_built, sqft, stories, property_type, and assessed_value
for properties missing these fields using USACE/FEMA's free NSI API.

API: https://nsi.sec.usace.army.mil/nsiapi/structures?fips={fips}
Data: Public domain (federal government). No auth required.
Queries by 11-digit tract FIPS (~1-3k structures) when possible.
Falls back to 5-digit county FIPS + spatial filter when census tract
vintages don't match (NSI may use different decennial boundaries).
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
import numpy as np
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from shapely.prepared import prep
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.property import Property

logger = logging.getLogger(__name__)

NSI_BASE_URL = "https://nsi.sec.usace.army.mil/nsiapi/structures"
NSI_CACHE_TTL = 3600  # 1 hour in-process cache
NSI_MATCH_RADIUS_M = 50.0

# Approximate meters per degree at Georgia's latitude (~34N)
_LAT_M = 111_000.0
_LON_M = 91_000.0  # cos(34°) * 111,000

# In-process tract-level cache: tract_geoid -> (timestamp, structures)
_NSI_CACHE: dict[str, tuple[float, list[dict]]] = {}

# Fields to keep from NSI response (minimize memory)
_KEEP_FIELDS = {"fd_id", "x", "y", "med_yr_blt", "sqft", "num_story",
                "occtype", "val_struct", "cbfips"}


async def fetch_nsi_tract(tract_geoid: str) -> list[dict]:
    """Fetch NSI structures for an 11-digit census tract FIPS."""
    url = f"{NSI_BASE_URL}?fips={tract_geoid}&fmt=fc"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    structures = []
    for f in data.get("features", []):
        props = f.get("properties")
        if not props or not props.get("x") or not props.get("y"):
            continue
        structures.append({k: props.get(k) for k in _KEEP_FIELDS})
    return structures


async def get_nsi_tract(tract_geoid: str) -> list[dict]:
    """Get NSI structures from in-process cache or fetch from API."""
    now = time.time()

    cached = _NSI_CACHE.get(tract_geoid)
    if cached and (now - cached[0]) < NSI_CACHE_TTL:
        return cached[1]

    logger.info("NSI: fetching structures for tract %s...", tract_geoid)
    try:
        structures = await fetch_nsi_tract(tract_geoid)
        _NSI_CACHE[tract_geoid] = (now, structures)
        logger.info("NSI: cached %d structures for tract %s", len(structures), tract_geoid)
        return structures
    except Exception as e:
        logger.error("NSI fetch failed for tract %s: %s", tract_geoid, e)
        return []


async def fetch_nsi_county(county_fips: str) -> list[dict]:
    """Fetch NSI structures for a 5-digit county FIPS.

    WARNING: Can return 50-350k structures for large counties.
    Only use for counties without ArcGIS adapters (typically smaller).
    """
    url = f"{NSI_BASE_URL}?fips={county_fips}&fmt=fc"
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    structures = []
    for f in data.get("features", []):
        props = f.get("properties")
        if not props or not props.get("x") or not props.get("y"):
            continue
        structures.append({k: props.get(k) for k in _KEEP_FIELDS})
    return structures


async def get_nsi_county(county_fips: str) -> list[dict]:
    """Get NSI structures for a county, with in-process caching."""
    now = time.time()
    key = f"county_{county_fips}"

    cached = _NSI_CACHE.get(key)
    if cached and (now - cached[0]) < NSI_CACHE_TTL:
        return cached[1]

    logger.info("NSI: fetching structures for county %s...", county_fips)
    try:
        structures = await fetch_nsi_county(county_fips)
        _NSI_CACHE[key] = (now, structures)
        logger.info("NSI: cached %d structures for county %s", len(structures), county_fips)
        return structures
    except Exception as e:
        logger.error("NSI county fetch failed for %s: %s", county_fips, e)
        return []


def filter_structures_to_tract(
    structures: list[dict],
    tract_geometry,
) -> list[dict]:
    """Spatially filter NSI structures to those within a tract boundary.

    Uses shapely prepared geometry for fast point-in-polygon tests.
    tract_geometry should be a GeoAlchemy2 geometry element.
    """
    shape = to_shape(tract_geometry)
    prepared = prep(shape)

    result = []
    for s in structures:
        x, y = s.get("x"), s.get("y")
        if x is not None and y is not None and prepared.contains(Point(x, y)):
            result.append(s)
    return result


def match_nearest(
    properties: list[Property],
    nsi_structures: list[dict],
    max_dist_m: float = NSI_MATCH_RADIUS_M,
) -> dict[str, dict]:
    """Match properties to nearest NSI structure within max_dist_m.

    Returns dict mapping str(Property.id) -> NSI structure dict.
    Uses numpy vectorized distance for efficiency.
    """
    if not properties or not nsi_structures:
        return {}

    nsi_xy = np.array(
        [(s["x"] * _LON_M, s["y"] * _LAT_M) for s in nsi_structures],
        dtype=np.float64,
    )

    matches: dict[str, dict] = {}
    for prop in properties:
        if prop.location is None:
            continue
        try:
            pt = to_shape(prop.location)
            px = pt.x * _LON_M
            py = pt.y * _LAT_M
            dists = np.sqrt((nsi_xy[:, 0] - px) ** 2 + (nsi_xy[:, 1] - py) ** 2)
            idx = int(np.argmin(dists))
            if dists[idx] <= max_dist_m:
                matches[str(prop.id)] = nsi_structures[idx]
        except Exception:
            continue

    return matches


def _classify_occtype(occtype: Optional[str]) -> Optional[str]:
    """Map NSI occupancy type to normalized property_type."""
    if not occtype:
        return None
    code = occtype.split("-")[0].upper()
    if code.startswith("RES"):
        return "residential"
    if code.startswith("COM"):
        return "commercial"
    if code.startswith("IND"):
        return "industrial"
    if code.startswith("AGR"):
        return "agricultural"
    return None


async def enrich_properties_from_nsi(
    db: AsyncSession,
    properties: list[Property],
    tract_geoid: str,
) -> int:
    """Enrich properties with NSI data for NULL fields only.

    Returns count of properties updated.
    """
    needs = [
        p for p in properties
        if any([
            p.year_built is None,
            p.square_footage is None,
            p.stories is None,
            p.property_type is None,
            p.assessed_value is None,
        ])
    ]
    if not needs:
        return 0

    nsi_structures = await get_nsi_tract(tract_geoid)
    if not nsi_structures:
        return 0

    logger.info("NSI: matching %d properties against %d structures in %s",
                len(needs), len(nsi_structures), tract_geoid)

    matches = match_nearest(needs, nsi_structures)
    if not matches:
        return 0

    current_year = datetime.now(timezone.utc).year
    updated = 0

    for prop in needs:
        nsi = matches.get(str(prop.id))
        if not nsi:
            continue

        changed = False
        provenance: dict[str, str] = {}

        if prop.year_built is None and nsi.get("med_yr_blt"):
            yr = int(nsi["med_yr_blt"])
            if 1800 < yr <= current_year:
                prop.year_built = yr
                prop.estimated_roof_age = current_year - yr
                provenance["year_built"] = "nsi"
                changed = True

        if prop.square_footage is None and nsi.get("sqft"):
            sqft = int(float(nsi["sqft"]))
            if sqft > 0:
                prop.square_footage = sqft
                provenance["sqft"] = "nsi"
                changed = True

        if prop.stories is None and nsi.get("num_story"):
            stories = int(nsi["num_story"])
            if stories > 0:
                prop.stories = stories
                provenance["stories"] = "nsi"
                changed = True

        if prop.property_type is None and nsi.get("occtype"):
            pt = _classify_occtype(nsi["occtype"])
            if pt:
                prop.property_type = pt
                provenance["property_type"] = "nsi"
                changed = True

        if prop.assessed_value is None and nsi.get("val_struct"):
            val = float(nsi["val_struct"])
            if val > 0:
                prop.assessed_value = val
                provenance["assessed_value"] = "nsi_replacement_cost"
                changed = True

        if changed:
            raw = dict(prop.raw_attributes) if prop.raw_attributes else {}
            raw["nsi_enriched"] = provenance
            prop.raw_attributes = raw
            updated += 1

    if updated:
        await db.commit()
        logger.info(
            "NSI enriched %d/%d properties in tract %s",
            updated, len(needs), tract_geoid,
        )

    return updated
