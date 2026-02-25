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


def _classify_nsi_occtype(occtype: Optional[str]) -> Optional[str]:
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


def _nsi_to_record(s: dict, county_fips: str) -> PropertyRecord:
    """Convert an NSI structure dict to a PropertyRecord."""
    yr = _safe_int(s.get("med_yr_blt"))
    sqft_raw = s.get("sqft")
    return PropertyRecord(
        parcel_id=str(s["fd_id"]),
        source_county="nsi",
        county_fips=county_fips,
        latitude=s.get("y"),
        longitude=s.get("x"),
        year_built=yr if yr and yr > 1800 else None,
        square_footage=_safe_int(float(sqft_raw)) if sqft_raw else None,
        stories=_safe_int(s.get("num_story")),
        property_type=_classify_nsi_occtype(s.get("occtype")),
        assessed_value=_safe_float(s.get("val_struct")),
        raw_attributes=s,
    )


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


def _extract_centroid(geometry: Optional[dict]) -> tuple[Optional[float], Optional[float]]:
    """Extract (lat, lon) from ArcGIS geometry (polygon centroid or point)."""
    if not geometry:
        return None, None
    if "rings" in geometry:
        coords = geometry["rings"][0]
        if not coords:
            return None, None
        lon = sum(c[0] for c in coords) / len(coords)
        lat = sum(c[1] for c in coords) / len(coords)
        return lat, lon
    if "x" in geometry:
        return geometry.get("y"), geometry.get("x")
    return None, None


def _build_address(*parts: Optional[str | int]) -> Optional[str]:
    """Join non-empty address parts into a single string."""
    cleaned = [str(p).strip() for p in parts if p is not None and str(p).strip()]
    return " ".join(cleaned) if cleaned else None


def _strip_table_prefix(attrs: dict) -> dict:
    """Strip 'TABLE.NAME.' prefix from ArcGIS joined-table field names.

    e.g. 'SDEWH.ITS.P_TAX_MASTER.OWNER1' -> 'OWNER1'
    """
    return {k.rsplit(".", 1)[-1]: v for k, v in attrs.items()}


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

    async def _fetch_tile(
        self,
        client: httpx.AsyncClient,
        xmin: float,
        ymin: float,
        xmax: float,
        ymax: float,
        *,
        max_pages: int = 10,
    ) -> list[PropertyRecord]:
        """Fetch parcels for a single bbox tile, handling pagination."""
        records: list[PropertyRecord] = []
        offset = 0

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

        return records

    async def fetch_by_bbox(
        self,
        xmin: float,
        ymin: float,
        xmax: float,
        ymax: float,
        *,
        max_depth: int = 3,
    ) -> list[PropertyRecord]:
        """Fetch parcels with adaptive bbox tiling for full coverage.

        Many county ArcGIS servers silently cap results at max_record_count
        without setting exceededTransferLimit. To handle this, we subdivide
        tiles that return exactly max_record_count results into 4 sub-tiles
        and re-fetch, up to max_depth levels.
        """
        seen_ids: set[str] = set()
        all_records: list[PropertyRecord] = []

        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            # Queue of (xmin, ymin, xmax, ymax, depth)
            tiles: list[tuple[float, float, float, float, int]] = [
                (xmin, ymin, xmax, ymax, 0)
            ]

            while tiles:
                tx0, ty0, tx1, ty1, depth = tiles.pop()
                records = await self._fetch_tile(client, tx0, ty0, tx1, ty1)

                # If we got exactly max_record_count, we likely hit the cap.
                # Subdivide into 4 quadrants and retry (up to max_depth).
                if len(records) >= self.max_record_count and depth < max_depth:
                    mx = (tx0 + tx1) / 2
                    my = (ty0 + ty1) / 2
                    tiles.append((tx0, ty0, mx, my, depth + 1))   # SW
                    tiles.append((mx, ty0, tx1, my, depth + 1))   # SE
                    tiles.append((tx0, my, mx, ty1, depth + 1))   # NW
                    tiles.append((mx, my, tx1, ty1, depth + 1))   # NE
                    logger.info(
                        "%s: tile at depth %d returned %d records (cap), subdividing into 4",
                        self.county_name, depth, len(records),
                    )
                    await asyncio.sleep(self.rate_limit_delay)
                    continue

                # Deduplicate across tiles
                for rec in records:
                    if rec.parcel_id not in seen_ids:
                        seen_ids.add(rec.parcel_id)
                        all_records.append(rec)

        logger.info("Fetched %d unique parcels from %s", len(all_records), self.county_name)
        return all_records


# ---------------------------------------------------------------------------
# Gwinnett County — verified fields from GC_Parcel/MapServer/6
# Joined table: P_Parcels + P_TAX_MASTER
# Available: PIN, address, owner, assessed/land/improvement values, acreage,
#   zoning, property class. NOT available: year_built, sqft, bedrooms/baths.
# ---------------------------------------------------------------------------
class GwinnettCountyAdapter(BaseCountyAdapter):
    county_name = "Gwinnett"
    county_fips = "13135"
    base_url = (
        "https://gis3.gwinnettcounty.com/mapvis/rest/services/"
        "GISDataBrowser/GC_Parcel/MapServer/6/query"
    )

    def normalize(self, attrs: dict, geometry: Optional[dict]) -> PropertyRecord:
        lat, lon = _extract_centroid(geometry)
        # Gwinnett returns joined-table prefixed keys:
        #   SDEWH.ITS.P_TAX_MASTER.OWNER1 -> strip to OWNER1
        a = _strip_table_prefix(attrs)

        address = (
            a.get("LOCADDR")
            or _build_address(a.get("STRNUM"), a.get("STRNAME"))
        )

        return PropertyRecord(
            parcel_id=str(a.get("PIN") or a.get("TAXPIN") or ""),
            source_county="gwinnett",
            county_fips=self.county_fips,
            address=address,
            owner_name=a.get("OWNER1"),
            assessed_value=_safe_float(a.get("TOTVAL1")),
            land_value=_safe_float(a.get("LANDVAL1")),
            improvement_value=_safe_float(a.get("DWLGVAL1")),
            lot_size_acres=_safe_float(
                a.get("DEEDEDACREAGE") or a.get("CALCULATEDACREAGE")
            ),
            zoning=a.get("ZONING"),
            land_use_code=a.get("PROPCLAS"),
            property_type=_classify_property_type(a.get("PROPCLAS")),
            latitude=lat,
            longitude=lon,
            raw_attributes=attrs,  # preserve original keys in raw
        )


# ---------------------------------------------------------------------------
# Fulton County — verified fields from Tax_ParcelCurrentDigest
# Available: parcel_id, address, owner, assessed/land/improvement values,
#   appraisal values, land acres, LU code, class code, living units.
# NOT available: year_built, sqft, bedrooms/baths, sale date/price.
# ---------------------------------------------------------------------------
class FultonCountyAdapter(BaseCountyAdapter):
    county_name = "Fulton"
    county_fips = "13121"
    base_url = (
        "https://gismaps.fultoncountyga.gov/arcgispub2/rest/services/"
        "Tax/Tax_ParcelCurrentDigest_GCS_WGS_1984/MapServer/0/query"
    )

    def normalize(self, attrs: dict, geometry: Optional[dict]) -> PropertyRecord:
        lat, lon = _extract_centroid(geometry)

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
            property_type=_classify_property_type(
                attrs.get("LUCode") or attrs.get("ClassCode")
            ),
            latitude=lat,
            longitude=lon,
            raw_attributes=attrs,
        )


# ---------------------------------------------------------------------------
# DeKalb County — verified fields from dcgis Parcels/MapServer/0
# Populated fields: PARCELID, SITEADDRESS, OWNERNME1, CNTASSDVAL,
#   TOTAPR1, ACREAGE, CLASSCD/CLASSDSCRP, STATEDAREA, ZONING.
# Schema has RESYRBLT/BLDGAREA/FLOORCOUNT but they are UNPOPULATED.
# ---------------------------------------------------------------------------
class DeKalbCountyAdapter(BaseCountyAdapter):
    county_name = "DeKalb"
    county_fips = "13089"
    base_url = (
        "https://dcgis.dekalbcountyga.gov/hosted/rest/services/"
        "Parcels/MapServer/0/query"
    )

    def normalize(self, attrs: dict, geometry: Optional[dict]) -> PropertyRecord:
        lat, lon = _extract_centroid(geometry)

        assessed = _safe_float(attrs.get("CNTASSDVAL"))
        land_val = _safe_float(attrs.get("LNDVALUE"))
        improvement = None
        if assessed and land_val:
            improvement = assessed - land_val if assessed > land_val else None

        return PropertyRecord(
            parcel_id=str(attrs.get("PARCELID") or ""),
            source_county="dekalb",
            county_fips=self.county_fips,
            address=attrs.get("SITEADDRESS"),
            owner_name=attrs.get("OWNERNME1"),
            year_built=_safe_int(attrs.get("RESYRBLT")),  # schema exists, rarely populated
            assessed_value=assessed,
            land_value=land_val,
            improvement_value=improvement,
            square_footage=_safe_int(
                attrs.get("BLDGAREA") or attrs.get("RESFLRAREA")
            ),
            lot_size_acres=_safe_float(attrs.get("ACREAGE")),
            lot_size_sqft=_safe_float(attrs.get("STATEDAREA")),
            zoning=attrs.get("ZONING"),
            land_use_code=attrs.get("CLASSCD"),
            property_type=_classify_property_type(attrs.get("CLASSCD")),
            stories=_safe_int(attrs.get("FLOORCOUNT")),
            latitude=lat,
            longitude=lon,
            raw_attributes=attrs,
        )


# ---------------------------------------------------------------------------
# Cobb County — verified fields from tax/taxassessorsdaily/MapServer/0
# Available: PIN, address, owner, assessed values (ASV_*), fair market
#   values (FMV_*), acreage, lot sqft, property class.
# NOT available: year_built, sqft, bedrooms/baths, sale date/price.
# ---------------------------------------------------------------------------
class CobbCountyAdapter(BaseCountyAdapter):
    county_name = "Cobb"
    county_fips = "13067"
    base_url = (
        "https://gis.cobbcounty.gov/gisserver/rest/services/"
        "tax/taxassessorsdaily/MapServer/0/query"
    )

    def normalize(self, attrs: dict, geometry: Optional[dict]) -> PropertyRecord:
        lat, lon = _extract_centroid(geometry)

        return PropertyRecord(
            parcel_id=str(attrs.get("PIN") or attrs.get("PARID") or ""),
            source_county="cobb",
            county_fips=self.county_fips,
            address=attrs.get("SITUS_ADDR"),
            owner_name=attrs.get("OWNER_NAM1"),
            assessed_value=_safe_float(attrs.get("ASV_TOTAL")),
            land_value=_safe_float(attrs.get("ASV_LAND") or attrs.get("FMV_LAND")),
            improvement_value=_safe_float(
                attrs.get("ASV_BLDG") or attrs.get("FMV_BLDG")
            ),
            lot_size_acres=_safe_float(attrs.get("ACRES") or attrs.get("ACRE_DEEDED")),
            lot_size_sqft=_safe_float(attrs.get("LAND_SQFT")),
            land_use_code=attrs.get("CLASS"),
            property_type=_classify_property_type(attrs.get("CLASS")),
            latitude=lat,
            longitude=lon,
            raw_attributes=attrs,
        )


# ---------------------------------------------------------------------------
# Cherokee County — verified fields from MainLayers/MapServer/1
# Available: PIN/TIN, Property_Address, Owner, Acreage, Zoning.
# NOT available: year_built, assessed_value, sqft, bedrooms/baths, sale info.
# Note: native CRS is State Plane GA West (WKID 2240); outSR=4326 in params.
# ---------------------------------------------------------------------------
class CherokeeCountyAdapter(BaseCountyAdapter):
    county_name = "Cherokee"
    county_fips = "13057"
    base_url = (
        "https://gis.cherokeecountyga.gov/arcgis/rest/services/"
        "MainLayers/MapServer/1/query"
    )

    def normalize(self, attrs: dict, geometry: Optional[dict]) -> PropertyRecord:
        lat, lon = _extract_centroid(geometry)

        return PropertyRecord(
            parcel_id=str(attrs.get("PIN") or attrs.get("TIN") or ""),
            source_county="cherokee",
            county_fips=self.county_fips,
            address=attrs.get("Property_Address"),
            owner_name=attrs.get("Owner"),
            lot_size_acres=_safe_float(attrs.get("Acreage")),
            zoning=attrs.get("Zoning"),
            latitude=lat,
            longitude=lon,
            raw_attributes=attrs,
        )


# ---------------------------------------------------------------------------
# Forsyth County — verified fields from Public/Tax_Parcel/MapServer/0
# Available: PARCELID, SITEADDRESS, RESYRBLT (year built), CNTASSDVAL,
#   LNDVALUE, BLDGAREA, RESFLRAREA, STATEDAREA, FLOORCOUNT, ZONING.
# NOT available: owner_name, bedrooms/baths, sale info.
# ---------------------------------------------------------------------------
class ForsythCountyAdapter(BaseCountyAdapter):
    county_name = "Forsyth"
    county_fips = "13117"
    base_url = (
        "https://geo.forsythco.com/gis/rest/services/"
        "Public/Tax_Parcel/MapServer/0/query"
    )

    def normalize(self, attrs: dict, geometry: Optional[dict]) -> PropertyRecord:
        lat, lon = _extract_centroid(geometry)

        assessed = _safe_float(attrs.get("CNTASSDVAL"))
        land_val = _safe_float(attrs.get("LNDVALUE"))
        improvement = None
        if assessed and land_val:
            improvement = assessed - land_val if assessed > land_val else None

        return PropertyRecord(
            parcel_id=str(attrs.get("PARCELID") or ""),
            source_county="forsyth",
            county_fips=self.county_fips,
            address=attrs.get("SITEADDRESS"),
            year_built=_safe_int(attrs.get("RESYRBLT")),
            assessed_value=assessed,
            land_value=land_val,
            improvement_value=improvement,
            square_footage=_safe_int(
                attrs.get("RESFLRAREA") or attrs.get("BLDGAREA")
            ),
            lot_size_sqft=_safe_float(attrs.get("STATEDAREA")),
            zoning=attrs.get("ZONING"),
            land_use_code=attrs.get("USECD"),
            property_type=_classify_property_type(attrs.get("USECD")),
            stories=_safe_int(attrs.get("FLOORCOUNT")),
            latitude=lat,
            longitude=lon,
            raw_attributes=attrs,
        )


# ---------------------------------------------------------------------------
# Douglas County — verified fields from MapLayers/MapServer/13
# BEST schema of all counties: Owner, PropertyAddress, yr_built, heatedarea,
#   no_bedrms, fullbaths, halfbaths, totalacres, curr_val, fmvres, ZONING_GIS.
# NOT available: sale date/price.
# ---------------------------------------------------------------------------
class DouglasCountyAdapter(BaseCountyAdapter):
    county_name = "Douglas"
    county_fips = "13097"
    base_url = (
        "https://maps.douglascountyga.gov/arcgis/rest/services/"
        "MapLayers/MapServer/13/query"
    )

    def normalize(self, attrs: dict, geometry: Optional[dict]) -> PropertyRecord:
        lat, lon = _extract_centroid(geometry)

        full_baths = _safe_int(attrs.get("fullbaths")) or 0
        half_baths = _safe_int(attrs.get("halfbaths")) or 0
        total_baths = full_baths + (half_baths * 0.5) if (full_baths or half_baths) else None

        return PropertyRecord(
            parcel_id=str(attrs.get("ParcelNo") or ""),
            source_county="douglas",
            county_fips=self.county_fips,
            address=attrs.get("PropertyAddress"),
            owner_name=attrs.get("Owner"),
            year_built=_safe_int(attrs.get("yr_built")),
            assessed_value=_safe_float(attrs.get("curr_val")),
            land_value=_safe_float(attrs.get("fmvres")),
            square_footage=_safe_int(attrs.get("heatedarea")),
            lot_size_acres=_safe_float(attrs.get("totalacres")),
            zoning=attrs.get("ZONING_GIS"),
            property_type=_classify_property_type(attrs.get("digclass")),
            bedrooms=_safe_int(attrs.get("no_bedrms")),
            bathrooms=total_baths,
            latitude=lat,
            longitude=lon,
            raw_attributes=attrs,
        )


# ---------------------------------------------------------------------------
# Clayton County — verified fields from ArcGIS Online Tax_Parcels/FeatureServer/0
# Available: PAN (parcel #), Owner1/2/3, Land_Value, Improvements, Total_Value,
#   Assessing_Primary_Use, Assessing_Neighborhood.
# NOT available: property address, year_built, sqft, bedrooms/baths, sale info.
# ---------------------------------------------------------------------------
class ClaytonCountyAdapter(BaseCountyAdapter):
    county_name = "Clayton"
    county_fips = "13063"
    base_url = (
        "https://services.arcgis.com/f4rR7WnIfGBdVYFd/arcgis/rest/services/"
        "Tax_Parcels/FeatureServer/0/query"
    )

    def normalize(self, attrs: dict, geometry: Optional[dict]) -> PropertyRecord:
        lat, lon = _extract_centroid(geometry)

        total_val = _safe_float(attrs.get("Total_Value"))
        land_val = _safe_float(attrs.get("Land_Value"))
        improvement = _safe_float(attrs.get("Improvements"))

        return PropertyRecord(
            parcel_id=str(attrs.get("PAN") or ""),
            source_county="clayton",
            county_fips=self.county_fips,
            owner_name=attrs.get("Owner1"),
            assessed_value=total_val,
            land_value=land_val,
            improvement_value=improvement,
            land_use_code=attrs.get("Assessing_Primary_Use"),
            property_type=_classify_property_type(attrs.get("Assessing_Primary_Use")),
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
    "13057": CherokeeCountyAdapter(),
    "13117": ForsythCountyAdapter(),
    "13097": DouglasCountyAdapter(),
    "13063": ClaytonCountyAdapter(),
}


# ---------------------------------------------------------------------------
# NSI-only path for counties without an ArcGIS adapter
# ---------------------------------------------------------------------------
async def _get_properties_from_nsi(
    db: AsyncSession,
    tract_geoid: str,
    county_fips: str,
    tract_geometry=None,
) -> tuple[list[Property], str | None, bool]:
    """Fetch properties from NSI for counties without an ArcGIS adapter.

    Tries tract-level FIPS query first. If empty (census tract vintage
    mismatch), falls back to county-level fetch + spatial filter using
    the tract boundary geometry.
    """
    # Check DB cache (same 30-day TTL)
    cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)
    cached_stmt = (
        select(Property)
        .where(Property.tract_geoid == tract_geoid, Property.fetched_at >= cutoff)
        .order_by(Property.year_built.asc().nullslast())
    )
    cached_result = await db.execute(cached_stmt)
    cached = list(cached_result.scalars().all())

    if cached:
        await db.execute(
            update(Property)
            .where(Property.tract_geoid == tract_geoid)
            .values(last_accessed_at=func.now())
        )
        await db.commit()

        # Backfill addresses if any are still missing
        if any(p.address is None and p.location is not None for p in cached):
            asyncio.create_task(_backfill_nsi_addresses(tract_geoid))

        return cached, "NSI", True

    # Cache miss — try tract-level NSI query first
    from app.services.nsi_enrichment import (
        get_nsi_tract, get_nsi_county, filter_structures_to_tract,
    )
    nsi_structures = []
    try:
        nsi_structures = await get_nsi_tract(tract_geoid)
    except Exception as e:
        logger.warning("NSI tract fetch failed for %s: %s", tract_geoid, e)

    # Tract-level empty — fall back to county-level + spatial filter
    if not nsi_structures and tract_geometry is not None:
        logger.info("NSI: tract %s empty, falling back to county %s + spatial filter",
                     tract_geoid, county_fips)
        try:
            county_structures = await get_nsi_county(county_fips)
            if county_structures:
                nsi_structures = filter_structures_to_tract(
                    county_structures, tract_geometry,
                )
                logger.info("NSI: filtered %d structures for tract %s from %d county structures",
                            len(nsi_structures), tract_geoid, len(county_structures))
        except Exception as e:
            logger.error("NSI county fallback failed for %s: %s", county_fips, e)

    if not nsi_structures:
        return [], "NSI", True

    records = [_nsi_to_record(s, county_fips) for s in nsi_structures]

    # Upsert (same pattern as ArcGIS path)
    now = datetime.now(timezone.utc)
    current_year = now.year
    rows = []
    for rec in records:
        roof_age = (current_year - rec.year_built) if rec.year_built and rec.year_built > 1800 else None
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
                "lot_size_sqft": None,
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

    # Deduplicate by (source_county, parcel_id)
    seen: dict[tuple[str, str], int] = {}
    for idx, row in enumerate(rows):
        key = (row["source_county"], row["parcel_id"])
        seen[key] = idx
    rows = [rows[i] for i in sorted(seen.values())]

    if rows:
        chunk_size = 500
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            stmt = insert(Property).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["source_county", "parcel_id"],
                set_={
                    "tract_geoid": stmt.excluded.tract_geoid,
                    "year_built": stmt.excluded.year_built,
                    "assessed_value": stmt.excluded.assessed_value,
                    "square_footage": stmt.excluded.square_footage,
                    "property_type": stmt.excluded.property_type,
                    "stories": stmt.excluded.stories,
                    "estimated_roof_age": stmt.excluded.estimated_roof_age,
                    "raw_attributes": stmt.excluded.raw_attributes,
                    "fetched_at": stmt.excluded.fetched_at,
                    "last_accessed_at": stmt.excluded.last_accessed_at,
                    "location": stmt.excluded.location,
                },
            )
            await db.execute(stmt)
        await db.commit()

    # Re-query ORM objects
    fresh_stmt = (
        select(Property)
        .where(Property.tract_geoid == tract_geoid)
        .order_by(Property.year_built.asc().nullslast())
    )
    fresh_result = await db.execute(fresh_stmt)
    properties = list(fresh_result.scalars().all())

    # Fire-and-forget: geocode addresses in background
    asyncio.create_task(_backfill_nsi_addresses(tract_geoid))

    return properties, "NSI", True


# ---------------------------------------------------------------------------
# Background address geocoding for NSI properties
# ---------------------------------------------------------------------------
async def _backfill_nsi_addresses(tract_geoid: str) -> None:
    """Background task: reverse-geocode addresses for NSI properties.

    Runs after NSI upsert. Processes sequentially at ~8 req/sec to stay
    under Mapbox's 600 req/min limit. Retries on 429 with backoff.
    """
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.services.geocoding import reverse_geocode_address

    if not settings.MAPBOX_TOKEN:
        return

    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(Property)
                .where(
                    Property.tract_geoid == tract_geoid,
                    Property.address.is_(None),
                    Property.location.isnot(None),
                )
            )
            result = await db.execute(stmt)
            properties = list(result.scalars().all())

            if not properties:
                return

            logger.info("Geocoding %d addresses for tract %s...",
                        len(properties), tract_geoid)

            geocoded = 0
            delay = 0.12  # ~8 req/sec, under Mapbox 600 req/min

            async with httpx.AsyncClient(timeout=5.0) as client:
                for i, prop in enumerate(properties):
                    try:
                        pt = to_shape(prop.location)
                        addr = await reverse_geocode_address(
                            pt.x, pt.y, settings.MAPBOX_TOKEN, client,
                        )
                        if addr:
                            prop.address = addr
                            geocoded += 1
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429:
                            # Back off on rate limit, then retry once
                            await asyncio.sleep(2.0)
                            try:
                                addr = await reverse_geocode_address(
                                    pt.x, pt.y, settings.MAPBOX_TOKEN, client,
                                )
                                if addr:
                                    prop.address = addr
                                    geocoded += 1
                            except Exception:
                                pass
                    except Exception:
                        pass

                    await asyncio.sleep(delay)

                    # Commit + log progress every 200 properties
                    if (i + 1) % 200 == 0:
                        await db.commit()
                        logger.info("Geocoded %d/%d so far for tract %s...",
                                    geocoded, i + 1, tract_geoid)

            if geocoded:
                await db.commit()
                logger.info("Geocoded %d/%d addresses for tract %s",
                            geocoded, len(properties), tract_geoid)

    except Exception as e:
        logger.error("Address backfill failed for tract %s: %s", tract_geoid, e)


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
        # No ArcGIS adapter — use NSI as primary data source
        return await _get_properties_from_nsi(db, tract_geoid, fips, tract.geometry)

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

    # Deduplicate by (source_county, parcel_id) — county APIs can return dupes
    seen: dict[tuple[str, str], int] = {}
    for idx, row in enumerate(rows):
        key = (row["source_county"], row["parcel_id"])
        seen[key] = idx  # last occurrence wins
    rows = [rows[i] for i in sorted(seen.values())]

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
    properties = list(fresh_result.scalars().all())

    # 6. NSI enrichment — fill NULL year_built/sqft/stories
    try:
        from app.services.nsi_enrichment import enrich_properties_from_nsi
        enriched = await enrich_properties_from_nsi(db, properties, tract_geoid)
        if enriched:
            fresh_result2 = await db.execute(fresh_stmt)
            properties = list(fresh_result2.scalars().all())
    except Exception as e:
        logger.warning("NSI enrichment skipped for %s: %s", tract_geoid, e)

    return properties, adapter.county_name, True


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
