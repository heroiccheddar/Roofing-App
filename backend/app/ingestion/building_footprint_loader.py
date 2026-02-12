"""Microsoft Building Footprints loader.

Downloads US building footprint data and aggregates building counts/areas
to census tract level for housing density scoring.

Data source: https://github.com/microsoft/USBuildingFootprints
"""

import json
import logging
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
from geoalchemy2.shape import to_shape
from shapely.geometry import Point, shape
from shapely.strtree import STRtree
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

# Microsoft Building Footprints download URLs (GeoJSON zips by state)
# Source: https://github.com/microsoft/USBuildingFootprints
FOOTPRINT_URLS = {
    "48": "https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/Texas.geojson.zip",
    "40": "https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/Oklahoma.geojson.zip",
    "20": "https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/Kansas.geojson.zip",
    "08": "https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/Colorado.geojson.zip",
    "31": "https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/Nebraska.geojson.zip",
    "13": "https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/Georgia.geojson.zip",
}


class BuildingFootprintError(Exception):
    """Exception raised for building footprint loading errors."""
    pass


async def download_footprints(state_fips: str, url: str) -> Path:
    """Download and extract Microsoft Building Footprints GeoJSONL file.

    Args:
        state_fips: Two-digit state FIPS code (e.g., '48' for Texas)
        url: Download URL for the state's GeoJSONL zip file

    Returns:
        Path to the extracted .geojsonl file

    Raises:
        BuildingFootprintError: If download or extraction fails

    Note:
        Files are 200MB-2GB compressed. Uses streaming download with
        generous timeout (300s). Creates temp directory that caller must clean up.
    """
    logger.info(f"Downloading building footprints for state {state_fips} from {url}")

    try:
        # Create temp directory for this state
        tmpdir = tempfile.mkdtemp(prefix=f"buildings_{state_fips}_")
        tmpdir_path = Path(tmpdir)

        # Download with streaming to handle large files
        async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()

                # Stream to temp zip file
                zip_path = tmpdir_path / f"{state_fips}_buildings.zip"
                total_bytes = 0

                with open(zip_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):  # 1MB chunks
                        f.write(chunk)
                        total_bytes += len(chunk)

                logger.info(f"Downloaded {total_bytes / (1024**2):.1f} MB for state {state_fips}")

        # Extract the zip file
        logger.info(f"Extracting building footprints for state {state_fips}")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmpdir_path)

        # Find the extracted GeoJSON file (.geojsonl or .geojson)
        geojsonl_files = list(tmpdir_path.glob("*.geojsonl")) + list(tmpdir_path.glob("*.geojson"))
        if not geojsonl_files:
            raise BuildingFootprintError(f"No .geojsonl/.geojson file found in zip for state {state_fips}")

        geojsonl_path = geojsonl_files[0]
        logger.info(f"Extracted {geojsonl_path.name} ({geojsonl_path.stat().st_size / (1024**2):.1f} MB)")

        # Clean up zip file to save disk space
        zip_path.unlink()

        return geojsonl_path

    except httpx.HTTPStatusError as e:
        raise BuildingFootprintError(f"HTTP error downloading footprints for state {state_fips}: {e}") from e
    except httpx.RequestError as e:
        raise BuildingFootprintError(f"Network error downloading footprints for state {state_fips}: {e}") from e
    except zipfile.BadZipFile as e:
        raise BuildingFootprintError(f"Invalid zip file for state {state_fips}: {e}") from e
    except Exception as e:
        raise BuildingFootprintError(f"Failed to download footprints for state {state_fips}: {e}") from e


async def load_tract_geometries(
    session: AsyncSession,
    state_fips: str,
) -> tuple[list[str], STRtree, list]:
    """Load census tract geometries for a state and build spatial index.

    Args:
        session: Async database session
        state_fips: Two-digit state FIPS code

    Returns:
        Tuple of (geoid_list, STRtree, geometry_list)
        - geoid_list: List of GEOIDs, parallel to geometry_list
        - STRtree: Spatial index for fast point-in-polygon queries
        - geometry_list: List of Shapely geometries, parallel to geoid_list

    Raises:
        BuildingFootprintError: If no tracts found for state
    """
    logger.info(f"Loading census tract geometries for state {state_fips}")

    # Query all tracts for this state
    result = await session.execute(
        select(CensusTract.geoid, CensusTract.geometry)
        .where(CensusTract.state_fips == state_fips)
    )
    rows = result.fetchall()

    if not rows:
        raise BuildingFootprintError(f"No census tracts found for state {state_fips}")

    # Convert WKB geometries to Shapely geometries
    geoids = []
    geometries = []

    for geoid, wkb_geom in rows:
        geoids.append(geoid)
        shapely_geom = to_shape(wkb_geom)
        geometries.append(shapely_geom)

    # Build spatial index
    tree = STRtree(geometries)

    logger.info(f"Loaded {len(geoids)} census tracts for state {state_fips}")

    return geoids, tree, geometries


def _iter_geojsonl_features(file_path: Path):
    """Yield GeoJSON features from a line-delimited GeoJSONL file."""
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _iter_geojson_features(file_path: Path):
    """Yield features from a standard GeoJSON FeatureCollection file.

    Uses ijson for memory-efficient streaming if available,
    otherwise falls back to loading the full file.
    """
    try:
        import ijson
        with open(file_path, "rb") as f:
            for feature in ijson.items(f, "features.item"):
                yield feature
    except ImportError:
        logger.warning("ijson not installed, loading full GeoJSON into memory (may use lots of RAM)")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        yield from data.get("features", [])


def aggregate_buildings_to_tracts(
    geojsonl_path: Path,
    geoids: list[str],
    tree: STRtree,
    geometries: list,
) -> dict[str, dict[str, Any]]:
    """Aggregate building footprints to census tracts.

    Processes building footprint file and assigns each building to its
    containing census tract. Supports both GeoJSONL (line-delimited) and
    standard GeoJSON FeatureCollection formats.

    Args:
        geojsonl_path: Path to .geojsonl or .geojson file with building footprints
        geoids: List of census tract GEOIDs (parallel to geometries)
        tree: STRtree spatial index for tracts
        geometries: List of census tract Shapely geometries (parallel to geoids)

    Returns:
        Dict mapping GEOID to stats:
        {
            "geoid": {
                "building_count": int,
                "total_area": float (square meters)
            }
        }
    """
    logger.info(f"Aggregating building footprints from {geojsonl_path.name}")

    # Accumulator: geoid -> {building_count, total_area}
    aggregates = defaultdict(lambda: {"building_count": 0, "total_area": 0.0})

    total_buildings = 0
    skipped_buildings = 0

    # Detect format: read first few lines to check for FeatureCollection
    is_feature_collection = False
    with open(geojsonl_path, "r", encoding="utf-8") as f:
        header = ""
        for _ in range(10):
            line = f.readline()
            if not line:
                break
            header += line
        if "FeatureCollection" in header:
            is_feature_collection = True

    if is_feature_collection:
        logger.info("Detected GeoJSON FeatureCollection format")
        features_iter = _iter_geojson_features(geojsonl_path)
    else:
        logger.info("Detected GeoJSONL (line-delimited) format")
        features_iter = _iter_geojsonl_features(geojsonl_path)

    for line_num, feature in enumerate(features_iter, 1):
        try:
            geom_dict = feature.get("geometry")
            properties = feature.get("properties", {})

            if not geom_dict:
                continue

            building_geom = shape(geom_dict)

            # Get building area (prefer properties, fallback to computed)
            area_sqm = properties.get("area_in_meters")
            if area_sqm is None:
                # Rough conversion from degrees² to m² at mid-latitudes
                area_sqm = building_geom.area * 12.364e9

            centroid = building_geom.centroid

            # Find containing tract via spatial index
            candidate_indices = tree.query(centroid)

            tract_geoid = None
            for idx in candidate_indices:
                if geometries[idx].contains(centroid):
                    tract_geoid = geoids[idx]
                    break

            if tract_geoid:
                aggregates[tract_geoid]["building_count"] += 1
                aggregates[tract_geoid]["total_area"] += area_sqm
                total_buildings += 1
            else:
                skipped_buildings += 1

            if line_num % 500000 == 0:
                logger.info(
                    f"  Processed {line_num:,} buildings "
                    f"({total_buildings:,} matched, {skipped_buildings:,} skipped)"
                )

        except Exception as e:
            if line_num <= 5:
                logger.warning(f"Error processing building {line_num}: {e}")
            continue

    logger.info(
        f"Aggregation complete: {total_buildings:,} buildings matched to "
        f"{len(aggregates)} tracts ({skipped_buildings:,} skipped)"
    )

    return dict(aggregates)


async def bulk_update_footprints(
    session: AsyncSession,
    aggregates: dict[str, dict[str, Any]],
    batch_size: int = 500,
) -> dict[str, int]:
    """Bulk update census tracts with building footprint aggregates.

    Args:
        session: Async database session
        aggregates: Dict mapping GEOID to {building_count, total_area}
        batch_size: Number of updates per batch

    Returns:
        Stats dict with "updated" and "errors" counts
    """
    if not aggregates:
        logger.warning("No aggregates to update")
        return {"updated": 0, "errors": 0}

    logger.info(f"Updating {len(aggregates)} census tracts with building footprint data")

    updated_count = 0
    error_count = 0

    # Process in batches
    geoids = list(aggregates.keys())
    for i in range(0, len(geoids), batch_size):
        batch_geoids = geoids[i : i + batch_size]

        try:
            # Update each tract in the batch
            for geoid in batch_geoids:
                stats = aggregates[geoid]
                building_count = stats["building_count"]
                total_area = stats["total_area"]

                # Compute average building area
                avg_area = total_area / building_count if building_count > 0 else None

                # Update the tract
                stmt = (
                    update(CensusTract)
                    .where(CensusTract.geoid == geoid)
                    .values(
                        building_count=building_count,
                        total_building_area_sqm=total_area,
                        avg_building_area_sqm=avg_area,
                    )
                )
                await session.execute(stmt)
                updated_count += 1

            # Commit batch
            await session.commit()
            logger.info(f"  Updated batch {i // batch_size + 1} ({len(batch_geoids)} tracts)")

        except Exception as e:
            logger.error(f"Error updating batch {i // batch_size + 1}: {e}")
            await session.rollback()
            error_count += len(batch_geoids)

    logger.info(f"Update complete: {updated_count} tracts updated, {error_count} errors")

    return {
        "updated": updated_count,
        "errors": error_count,
    }


async def load_building_footprints(
    state_fips_codes: list[str],
    session: AsyncSession,
) -> dict[str, int]:
    """Load Microsoft Building Footprints for given states.

    Orchestrates the full pipeline:
    1. Download building footprint GeoJSONL for each state
    2. Load census tract geometries and build spatial index
    3. Aggregate building counts/areas to tracts
    4. Bulk update census_tracts table
    5. Clean up temp files

    Args:
        state_fips_codes: List of 2-digit state FIPS codes (e.g., ['48', '40'])
        session: Async database session

    Returns:
        Dict with aggregate stats:
        - states_processed: Number of states successfully processed
        - total_buildings: Total number of buildings matched
        - total_tracts_updated: Total number of tracts updated
        - errors: Number of states that failed

    Example:
        >>> result = await load_building_footprints(['48'], session)
        >>> print(f"Processed {result['total_buildings']:,} buildings")
    """
    total_states_processed = 0
    total_buildings_matched = 0
    total_tracts_updated = 0
    total_errors = 0

    logger.info(f"Starting building footprint load for {len(state_fips_codes)} states")

    for state_fips in state_fips_codes:
        if state_fips not in FOOTPRINT_URLS:
            logger.warning(f"No footprint URL for state {state_fips}, skipping")
            total_errors += 1
            continue

        geojsonl_path = None
        tmpdir = None

        try:
            logger.info(f"Processing state {state_fips}")

            # Download building footprints
            url = FOOTPRINT_URLS[state_fips]
            geojsonl_path = await download_footprints(state_fips, url)
            tmpdir = geojsonl_path.parent

            # Load tract geometries
            geoids, tree, geometries = await load_tract_geometries(session, state_fips)

            # Aggregate buildings to tracts
            aggregates = aggregate_buildings_to_tracts(geojsonl_path, geoids, tree, geometries)

            # Bulk update tracts
            update_stats = await bulk_update_footprints(session, aggregates, batch_size=500)

            # Accumulate stats
            total_states_processed += 1
            total_buildings_matched += sum(agg["building_count"] for agg in aggregates.values())
            total_tracts_updated += update_stats["updated"]

            logger.info(
                f"State {state_fips} complete: {len(aggregates)} tracts updated "
                f"with building footprint data"
            )

        except BuildingFootprintError as e:
            logger.error(f"Failed to load footprints for state {state_fips}: {e}")
            total_errors += 1
        except Exception as e:
            logger.error(f"Unexpected error loading footprints for state {state_fips}: {e}", exc_info=True)
            total_errors += 1
        finally:
            # Clean up temp files
            if tmpdir and Path(tmpdir).exists():
                try:
                    import shutil
                    shutil.rmtree(tmpdir)
                    logger.info(f"Cleaned up temp directory for state {state_fips}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp directory {tmpdir}: {e}")

    logger.info(
        f"Building footprint load complete: {total_states_processed} states processed, "
        f"{total_buildings_matched:,} buildings matched, "
        f"{total_tracts_updated} tracts updated, "
        f"{total_errors} errors"
    )

    return {
        "states_processed": total_states_processed,
        "total_buildings": total_buildings_matched,
        "total_tracts_updated": total_tracts_updated,
        "errors": total_errors,
    }
