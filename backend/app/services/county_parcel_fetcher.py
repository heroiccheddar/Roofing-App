"""County GIS ArcGIS REST API adapters for parcel data.

Each county adapter maps its specific ArcGIS REST field names to a
normalized PropertyRecord dataclass. New counties are added by
subclassing BaseCountyAdapter and registering in COUNTY_ADAPTERS.

On-demand fetch with database caching: parcels are fetched from county
APIs when first requested and cached in the properties table. Stale
entries (>30 days) are re-fetched; unaccessed entries (>60 days) are evicted.
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import delete, select, update, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract
from app.models.property import Property

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 30
EVICTION_DAYS = 60


# ---------------------------------------------------------------------------
# Normalized record returned by all adapters
# ---------------------------------------------------------------------------
@dataclass
class PropertyRecord:
    parcel_id: str
    source_county: str
    county_fips: str
    address: Optional[str] = None
    owner_name: Optional[str] = None
    year_built: Optional[int] = None
    assessed_value: Optional[float] = None
    land_value: Optional[float] = None
    improvement_value: Optional[float] = None
    square_footage: Optional[int] = None
    lot_size_sqft: Optional[float] = None
    lot_size_acres: Optional[float] = None
    zoning: Optional[str] = None
    land_use_code: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    stories: Optional[int] = None
    last_sale_date: Optional[date] = None
    last_sale_price: Optional[float] = None
    roof_material: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    raw_attributes: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        v = int(val)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        v = float(val)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_epoch_ms(val) -> Optional[date]:
    """Parse ArcGIS epoch-millisecond date fields."""
    if val is None:
        return None
    try:
        ts = int(val) / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).date()
    except (ValueError, TypeError, OSError):
        return None


def _classify_property_type(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    c = str(code).strip().upper()
    if c.startswith("R") or c in ("100", "101", "102", "109"):
        return "residential"
    if c.startswith("C") or c in ("300", "301", "302"):
        return "commercial"
    if c.startswith("I") or c in ("400", "401"):
        return "industrial"
    if c.startswith("A") or c in ("600", "601"):
        return "agricultural"
    return code.lower()


# ---------------------------------------------------------------------------
# Base adapter
# ---------------------------------------------------------------------------
class BaseCountyAdapter(ABC):
    county_name: str
    county_fips: str
    base_url: str
    max_record_count: int = 1000
    out_fields: str = "*"
    rate_limit_delay: float = 0.5

    @abstractmethod
    def normalize(self, attrs: dict, geometry: Optional[dict]) -> PropertyRecord:
        ...

    async def fetch_by_bbox(
        self,
        xmin: float,
        ymin: float,
        xmax: float,
        ymax: float,
        *,
        max_pages: int = 10,
    ) -> list[PropertyRecord]:
        records: list[PropertyRecord] = []
        offset = 0

        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            for _ in range(max_pages):
                params = {
                    "geometry": f'{{"xmin":{xmin},"ymin":{ymin},"xmax":{xmax},"ymax":{ymax}}}',
                    "geometryType": "esriGeometryEnvelope",
                    "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": self.out_fields,
                    "returnGeometry": "true",
                    "resultOffset": str(offset),
                    "resultRecordCount": str(self.max_record_count),
                    "f": "json",
                    "outSR": "4326",
                }
                try:
                    resp = await client.get(self.base_url, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.error("Error fetching parcels from %s: %s", self.county_name, e)
                    break

                features = data.get("features", [])
                if not features:
                    break

                for feat in features:
                    attrs = feat.get("attributes", {})
                    geom = feat.get("geometry")
                    try:
                        rec = self.normalize(attrs, geom)
                        if rec.parcel_id:
                            records.append(rec)
                    except Exception as e:
                        logger.debug("Skip parcel in %s: %s", self.county_name, e)

                if not data.get("exceededTransferLimit") or len(features) < self.max_record_count:
                    break
                offset += len(features)
                await asyncio.sleep(self.rate_limit_delay)

        logger.info("Fetched %d parcels from %s", len(records), self.county_name)
        return records


# ---------------------------------------------------------------------------
# Gwinnett County — verified fields
# ---------------------------------------------------------------------------
class GwinnettCountyAdapter(BaseCountyAdapter):
    county_name = "Gwinnett"
    county_fips = "13135"
    base_url = (
        "https://gis3.gwinnettcounty.com/mapvis/rest/services/"
        "GISDataBrowser/GC_Parcel/MapServer/6/query"
    )

    def normalize(self, attrs: dict, geometry: Optional[dict]) -> PropertyRecord:
        lat, lon = None, None
        if geometry:
            # Polygon centroid or point
            if "rings" in geometry:
                coords = geometry["rings"][0]
                lon = sum(c[0] for c in coords) / len(coords)
                lat = sum(c[1] for c in coords) / len(coords)
            elif "x" in geometry:
                lon, lat = geometry["x"], geometry["y"]

        addr_parts = [str(attrs.get("STRNUM") or ""), attrs.get("STRNAME") or ""]
        address = " ".join(p for p in addr_parts if p).strip() or attrs.get("LOCADDR")

        return PropertyRecord(
            parcel_id=str(attrs.get("PIN") or attrs.get("TAXPIN") or ""),
            source_county="gwinnett",
            county_fips=self.county_fips,
            address=address,
            owner_name=attrs.get("OWNER1"),
            assessed_value=_safe_float(attrs.get("TOTVAL1")),
            land_value=_safe_float(attrs.get("LANDVAL1")),
            improvement_value=_safe_float(attrs.get("DWLGVAL1")),
            lot_size_acres=_safe_float(attrs.get("DEEDEDACREAGE") or attrs.get("CALCULATEDACREAGE")),
            zoning=attrs.get("ZONING"),
            land_use_code=attrs.get("PROPCLAS"),
            property_type=_classify_property_type(attrs.get("PROPCLAS")),
            latitude=lat,
            longitude=lon,
            raw_attributes=attrs,
        )


# ---------------------------------------------------------------------------
# Fulton County — verified fields
# ---------------------------------------------------------------------------
class FultonCountyAdapter(BaseCountyAdapter):
    county_name = "Fulton"
    county_fips = "13121"
    base_url = (
        "https://gismaps.fultoncountyga.gov/arcgispub2/rest/services/"
        "PropertyMapViewer/PropertyMapViewer/MapServer/11/query"
    )

    def normalize(self, attrs: dict, geometry: Optional[dict]) -> PropertyRecord:
        lat, lon = None, None
        if geometry:
            if "rings" in geometry:
                coords = geometry["rings"][0]
                lon = sum(c[0] for c in coords) / len(coords)
                lat = sum(c[1] for c in coords) / len(coords)
            elif "x" in geometry:
                lon, lat = geometry["x"], geometry["y"]

        return PropertyRecord(
            parcel_id=str(attrs.get("ParcelID") or ""),
            source_county="fulton",
            county_fips=self.county_fips,
            address=attrs.get("Address"),
            owner_name=attrs.get("Owner"),
            assessed_value=_safe_float(attrs.get("TotAssess")),
            land_value=_safe_float(attrs.get("LandAssess")),
            improvement_value=_safe_float(attrs.get("ImprAssess")),
            lot_size_acres=_safe_float(attrs.get("LandAcres")),
            land_use_code=attrs.get("LUCode"),
            property_type=_classify_property_type(attrs.get("LUCode") or attrs.get("ClassCode")),
            latitude=lat,
            longitude=lon,
            raw_attributes=attrs,
        )


# ---------------------------------------------------------------------------
# DeKalb County — partial field verification
# ---------------------------------------------------------------------------
class DeKalbCountyAdapter(BaseCountyAdapter):
    county_name = "DeKalb"
    county_fips = "13089"
    base_url = (
        "https://gis.dekalbcountyga.gov/arcgis/rest/services/"
        "Parcels/MapServer/0/query"
    )

    def normalize(self, attrs: dict, geometry: Optional[dict]) -> PropertyRecord:
        lat, lon = None, None
        if geometry:
            if "rings" in geometry:
                coords = geometry["rings"][0]
                lon = sum(c[0] for c in coords) / len(coords)
                lat = sum(c[1] for c in coords) / len(coords)
            elif "x" in geometry:
                lon, lat = geometry["x"], geometry["y"]

        return PropertyRecord(
            parcel_id=str(
                attrs.get("PARCELID") or attrs.get("PIN") or attrs.get("PARCEL_ID") or ""
            ),
            source_county="dekalb",
            county_fips=self.county_fips,
            address=attrs.get("SITE_ADDR") or attrs.get("ADDRESS") or attrs.get("LOCATION"),
            owner_name=attrs.get("OWNER") or attrs.get("OWNER_NAME") or attrs.get("OWNERNAME"),
            year_built=_safe_int(attrs.get("YEAR_BUILT") or attrs.get("YEARBUILT")),
            assessed_value=_safe_float(
                attrs.get("CNTASSDVAL") or attrs.get("TOTAL_VALUE") or attrs.get("ASSESSED_VALUE")
            ),
            land_value=_safe_float(attrs.get("LAND_VALUE") or attrs.get("LANDVALUE")),
            improvement_value=_safe_float(
                attrs.get("IMPROVEMENT_VALUE") or attrs.get("IMPRVALUE")
            ),
            square_footage=_safe_int(attrs.get("SQ_FT") or attrs.get("SQFT") or attrs.get("HEATED_SQFT")),
            lot_size_acres=_safe_float(attrs.get("ACREAGE") or attrs.get("ACRES")),
            zoning=attrs.get("ZONING"),
            land_use_code=attrs.get("LAND_USE") or attrs.get("LANDUSE"),
            property_type=_classify_property_type(
                attrs.get("LAND_USE") or attrs.get("LANDUSE")
            ),
            latitude=lat,
            longitude=lon,
            raw_attributes=attrs,
        )


# ---------------------------------------------------------------------------
# Cobb County — open data portal (GeoJSON endpoint)
# ---------------------------------------------------------------------------
class CobbCountyAdapter(BaseCountyAdapter):
    county_name = "Cobb"
    county_fips = "13067"
    # Cobb uses open data portal — try ArcGIS Hub feature layer
    base_url = (
        "https://services1.arcgis.com/XBhYkoXKJCRHBEAu/arcgis/rest/services/"
        "Cobb_County_Parcels/FeatureServer/0/query"
    )

    def normalize(self, attrs: dict, geometry: Optional[dict]) -> PropertyRecord:
        lat, lon = None, None
        if geometry:
            if "rings" in geometry:
                coords = geometry["rings"][0]
                lon = sum(c[0] for c in coords) / len(coords)
                lat = sum(c[1] for c in coords) / len(coords)
            elif "x" in geometry:
                lon, lat = geometry["x"], geometry["y"]

        return PropertyRecord(
            parcel_id=str(
                attrs.get("PARCEL_ID") or attrs.get("PIN") or attrs.get("ParcelID") or ""
            ),
            source_county="cobb",
            county_fips=self.county_fips,
            address=(
                attrs.get("SITE_ADDR") or attrs.get("ADDRESS") or attrs.get("LOCATION") or attrs.get("SiteAddress")
            ),
            owner_name=attrs.get("OWNER") or attrs.get("OWNER_NAME") or attrs.get("OwnerName"),
            year_built=_safe_int(attrs.get("YEAR_BUILT") or attrs.get("YearBuilt")),
            assessed_value=_safe_float(
                attrs.get("TOTAL_APPRAISAL") or attrs.get("ASSESSED_VALUE") or attrs.get("TotalValue")
            ),
            land_value=_safe_float(attrs.get("LAND_APPRAISAL") or attrs.get("LandValue")),
            improvement_value=_safe_float(
                attrs.get("IMPROVEMENT_APPRAISAL") or attrs.get("ImprovementValue")
            ),
            square_footage=_safe_int(
                attrs.get("TOTAL_SQ_FT") or attrs.get("HEATED_SQ_FT") or attrs.get("SqFt")
            ),
            lot_size_acres=_safe_float(attrs.get("ACREAGE") or attrs.get("ACRES") or attrs.get("Acres")),
            zoning=attrs.get("ZONING") or attrs.get("Zoning"),
            land_use_code=attrs.get("LAND_USE_CODE") or attrs.get("LandUse"),
            property_type=_classify_property_type(
                attrs.get("LAND_USE_CODE") or attrs.get("LandUse")
            ),
            bedrooms=_safe_int(attrs.get("BEDROOMS") or attrs.get("Bedrooms")),
            bathrooms=_safe_float(attrs.get("BATHROOMS") or attrs.get("Bathrooms")),
            last_sale_date=_parse_epoch_ms(attrs.get("SALE_DATE") or attrs.get("SaleDate")),
            last_sale_price=_safe_float(attrs.get("SALE_PRICE") or attrs.get("SalePrice")),
            latitude=lat,
            longitude=lon,
            raw_attributes=attrs,
        )


# ---------------------------------------------------------------------------
# Registry — keyed by 5-digit FIPS (state + county)
# ---------------------------------------------------------------------------
COUNTY_ADAPTERS: dict[str, BaseCountyAdapter] = {
    "13135": GwinnettCountyAdapter(),
    "13121": FultonCountyAdapter(),
    "13089": DeKalbCountyAdapter(),
    "13067": CobbCountyAdapter(),
}


# ---------------------------------------------------------------------------
# Fetch + cache orchestrator
# ---------------------------------------------------------------------------
async def get_properties_for_tract(
    db: AsyncSession,
    tract_geoid: str,
) -> tuple[list[Property], str | None, bool]:
    """Get properties for a census tract, fetching from county API if needed.

    Returns:
        (properties, source_county_name, has_adapter)
    """
    # 1. Look up tract for county info + geometry
    tract_stmt = select(CensusTract).where(CensusTract.geoid == tract_geoid)
    tract_result = await db.execute(tract_stmt)
    tract = tract_result.scalar_one_or_none()
    if tract is None:
        return [], None, False

    fips = (tract.state_fips or "") + (tract.county_fips or "")
    adapter = COUNTY_ADAPTERS.get(fips)
    if adapter is None:
        return [], None, False

    # 2. Check DB cache
    cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)
    cached_stmt = (
        select(Property)
        .where(
            Property.tract_geoid == tract_geoid,
            Property.fetched_at >= cutoff,
        )
        .order_by(Property.year_built.asc().nullslast())
    )
    cached_result = await db.execute(cached_stmt)
    cached = list(cached_result.scalars().all())

    if cached:
        # Update last_accessed_at for LRU
        await db.execute(
            update(Property)
            .where(Property.tract_geoid == tract_geoid)
            .values(last_accessed_at=func.now())
        )
        await db.commit()
        return cached, adapter.county_name, True

    # 3. Cache miss — fetch from county API
    try:
        tract_shape = to_shape(tract.geometry)
        bounds = tract_shape.bounds  # (minx, miny, maxx, maxy)
        records = await adapter.fetch_by_bbox(bounds[0], bounds[1], bounds[2], bounds[3])
    except Exception as e:
        logger.error("Failed to fetch parcels for tract %s: %s", tract_geoid, e)
        return [], adapter.county_name, True

    if not records:
        return [], adapter.county_name, True

    # 4. Bulk upsert
    now = datetime.now(timezone.utc)
    current_year = now.year
    rows = []
    for rec in records:
        roof_age = (current_year - rec.year_built) if rec.year_built and rec.year_built > 1800 else None
        lot_sqft = (rec.lot_size_acres * 43560) if rec.lot_size_acres else rec.lot_size_sqft

        rows.append(
            {
                "id": uuid.uuid4(),
                "county_fips": rec.county_fips,
                "parcel_id": rec.parcel_id,
                "source_county": rec.source_county,
                "tract_geoid": tract_geoid,
                "location": f"SRID=4326;POINT({rec.longitude} {rec.latitude})"
                if rec.latitude and rec.longitude
                else None,
                "address": rec.address,
                "owner_name": rec.owner_name,
                "year_built": rec.year_built,
                "assessed_value": rec.assessed_value,
                "land_value": rec.land_value,
                "improvement_value": rec.improvement_value,
                "square_footage": rec.square_footage,
                "lot_size_sqft": lot_sqft,
                "lot_size_acres": rec.lot_size_acres,
                "zoning": rec.zoning,
                "land_use_code": rec.land_use_code,
                "property_type": rec.property_type,
                "bedrooms": rec.bedrooms,
                "bathrooms": rec.bathrooms,
                "stories": rec.stories,
                "last_sale_date": rec.last_sale_date,
                "last_sale_price": rec.last_sale_price,
                "estimated_roof_age": roof_age,
                "roof_material": rec.roof_material,
                "raw_attributes": rec.raw_attributes,
                "fetched_at": now,
                "last_accessed_at": now,
            }
        )

    if rows:
        # Batch in chunks to avoid oversized queries
        chunk_size = 500
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            stmt = insert(Property).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["source_county", "parcel_id"],
                set_={
                    "tract_geoid": stmt.excluded.tract_geoid,
                    "address": stmt.excluded.address,
                    "owner_name": stmt.excluded.owner_name,
                    "year_built": stmt.excluded.year_built,
                    "assessed_value": stmt.excluded.assessed_value,
                    "land_value": stmt.excluded.land_value,
                    "improvement_value": stmt.excluded.improvement_value,
                    "square_footage": stmt.excluded.square_footage,
                    "lot_size_sqft": stmt.excluded.lot_size_sqft,
                    "lot_size_acres": stmt.excluded.lot_size_acres,
                    "zoning": stmt.excluded.zoning,
                    "land_use_code": stmt.excluded.land_use_code,
                    "property_type": stmt.excluded.property_type,
                    "bedrooms": stmt.excluded.bedrooms,
                    "bathrooms": stmt.excluded.bathrooms,
                    "stories": stmt.excluded.stories,
                    "last_sale_date": stmt.excluded.last_sale_date,
                    "last_sale_price": stmt.excluded.last_sale_price,
                    "estimated_roof_age": stmt.excluded.estimated_roof_age,
                    "raw_attributes": stmt.excluded.raw_attributes,
                    "fetched_at": stmt.excluded.fetched_at,
                    "last_accessed_at": stmt.excluded.last_accessed_at,
                    "location": stmt.excluded.location,
                },
            )
            await db.execute(stmt)
        await db.commit()

    # 5. Re-query to get ORM objects
    fresh_stmt = (
        select(Property)
        .where(Property.tract_geoid == tract_geoid)
        .order_by(Property.year_built.asc().nullslast())
    )
    fresh_result = await db.execute(fresh_stmt)
    return list(fresh_result.scalars().all()), adapter.county_name, True


async def evict_stale_properties(db: AsyncSession) -> int:
    """Delete properties not accessed in EVICTION_DAYS days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=EVICTION_DAYS)
    stmt = delete(Property).where(Property.last_accessed_at < cutoff)
    result = await db.execute(stmt)
    await db.commit()
    count = result.rowcount
    if count:
        logger.info("Evicted %d stale properties", count)
    return count
