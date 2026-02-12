"""USFS NLCD Tree Canopy Coverage loader.

Reads NLCD Tree Canopy Cover (TCC) GeoTIFF rasters and aggregates to
census tracts using rasterio-based zonal statistics. Computes mean, max,
std, and a composite risk score for tree canopy coverage (0-100%).

Data source: USDA Forest Service / MRLC Consortium
Format: 30m resolution GeoTIFF, values 0-100 (percent canopy cover)
Download: https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/
"""

import logging
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds
from rasterio.warp import transform_geom
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping, shape
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)


class TreeCanopyLoaderError(Exception):
    """Exception raised for tree canopy loading errors."""
    pass


async def load_tract_geometries(
    session: AsyncSession,
    state_fips: str,
) -> list[tuple[str, Any]]:
    """Load census tract geometries for a state as shapely objects.

    Args:
        session: Async database session
        state_fips: Two-digit state FIPS code (e.g., '13' for Georgia)

    Returns:
        List of (geoid, shapely_geometry) tuples

    Raises:
        TreeCanopyLoaderError: If no tracts found for state
    """
    logger.info(f"Loading census tract geometries for state {state_fips}")

    result = await session.execute(
        select(CensusTract.geoid, CensusTract.geometry)
        .where(CensusTract.state_fips == state_fips)
    )
    rows = result.fetchall()

    if not rows:
        raise TreeCanopyLoaderError(f"No census tracts found for state {state_fips}")

    tract_geoms = []
    for geoid, wkb_geom in rows:
        shapely_geom = to_shape(wkb_geom)
        tract_geoms.append((geoid, shapely_geom))

    logger.info(f"Loaded {len(tract_geoms)} census tracts for state {state_fips}")
    return tract_geoms


def _compute_zonal_stats_for_tract(
    src: rasterio.DatasetReader,
    geom_geojson: dict,
) -> dict[str, float | None]:
    """Compute zonal statistics for a single tract polygon.

    Reads the raster window covering the tract bounding box, masks by
    the tract polygon, and computes mean/max/std on valid pixels.

    Args:
        src: Open rasterio dataset
        geom_geojson: Tract geometry as GeoJSON dict (in raster CRS)

    Returns:
        Dict with mean, max, std (or all None if no valid pixels)
    """
    try:
        geom_shape = shape(geom_geojson)
        bounds = geom_shape.bounds  # (minx, miny, maxx, maxy)

        # Convert bounds to pixel window
        window = rasterio.windows.from_bounds(*bounds, transform=src.transform)

        # Clamp to raster extent
        window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))

        if window.width < 1 or window.height < 1:
            return {"mean": None, "max": None, "std": None}

        # Round to integer pixel window
        window = window.round_offsets().round_lengths()
        if window.width < 1 or window.height < 1:
            return {"mean": None, "max": None, "std": None}

        # Read the raster data for this window
        data = src.read(1, window=window)
        win_transform = src.window_transform(window)

        # Create mask from polygon geometry
        mask = geometry_mask(
            [geom_geojson],
            out_shape=data.shape,
            transform=win_transform,
            all_touched=True,
            invert=True,  # True inside polygon
        )

        # Apply mask + nodata filter
        nodata = src.nodata if src.nodata is not None else 255
        valid = mask & (data != nodata) & (data >= 0) & (data <= 100)

        if not valid.any():
            return {"mean": None, "max": None, "std": None}

        valid_pixels = data[valid].astype(float)

        return {
            "mean": float(np.mean(valid_pixels)),
            "max": float(np.max(valid_pixels)),
            "std": float(np.std(valid_pixels)),
        }

    except Exception as e:
        logger.debug(f"Error computing zonal stats: {e}")
        return {"mean": None, "max": None, "std": None}


def aggregate_canopy_to_tracts(
    tif_path: Path,
    tract_geoms: list[tuple[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Aggregate tree canopy coverage to census tracts via zonal statistics.

    Uses rasterio windowed reads to compute mean, max, and std of canopy
    coverage (0-100%) for each tract polygon from the 30m NLCD raster.

    Args:
        tif_path: Path to NLCD TCC GeoTIFF file
        tract_geoms: List of (geoid, shapely_geometry) tuples

    Returns:
        Dict mapping GEOID to computed stats
    """
    logger.info(f"Computing zonal statistics from {tif_path.name} for {len(tract_geoms)} tracts")

    aggregates = {}
    skipped = 0

    with rasterio.open(str(tif_path)) as src:
        raster_crs = src.crs
        logger.info(f"Raster CRS: {raster_crs}, size: {src.width}x{src.height}, nodata: {src.nodata}")

        for idx, (geoid, geom) in enumerate(tract_geoms):
            # Reproject tract geometry from WGS84 to raster CRS if needed
            geom_geojson = mapping(geom)
            if raster_crs and str(raster_crs) != "EPSG:4326":
                try:
                    geom_geojson = transform_geom(
                        "EPSG:4326", raster_crs, geom_geojson
                    )
                except Exception as e:
                    logger.debug(f"CRS transform failed for {geoid}: {e}")
                    skipped += 1
                    continue

            # Compute zonal statistics
            stats = _compute_zonal_stats_for_tract(src, geom_geojson)

            if stats["mean"] is None:
                skipped += 1
                continue

            mean_pct = stats["mean"]
            max_pct = stats["max"] or 0.0
            std_pct = stats["std"] or 0.0

            # Risk score: weighted combination of mean and max coverage
            risk_score = min(mean_pct * 0.7 + max_pct * 0.3, 100.0)

            aggregates[geoid] = {
                "mean_pct": round(mean_pct, 2),
                "max_pct": round(max_pct, 2),
                "std_pct": round(std_pct, 2),
                "risk_score": round(risk_score, 2),
            }

            if (idx + 1) % 500 == 0:
                logger.info(f"  Processed {idx + 1}/{len(tract_geoms)} tracts...")

    logger.info(
        f"Zonal stats complete: {len(aggregates)} tracts with data, "
        f"{skipped} tracts skipped (no raster coverage)"
    )
    return aggregates


async def bulk_update_canopy(
    session: AsyncSession,
    aggregates: dict[str, dict[str, Any]],
    batch_size: int = 500,
) -> dict[str, int]:
    """Bulk update census tracts with tree canopy data.

    Args:
        session: Async database session
        aggregates: Dict mapping GEOID to {mean_pct, max_pct, std_pct, risk_score}
        batch_size: Number of updates per batch

    Returns:
        Stats dict with "updated" and "errors" counts
    """
    if not aggregates:
        logger.warning("No aggregates to update")
        return {"updated": 0, "errors": 0}

    logger.info(f"Updating {len(aggregates)} census tracts with tree canopy data")

    updated_count = 0
    error_count = 0
    geoids = list(aggregates.keys())

    for i in range(0, len(geoids), batch_size):
        batch_geoids = geoids[i : i + batch_size]

        try:
            for geoid in batch_geoids:
                stats = aggregates[geoid]
                stmt = (
                    update(CensusTract)
                    .where(CensusTract.geoid == geoid)
                    .values(
                        tree_canopy_mean_pct=stats["mean_pct"],
                        tree_canopy_max_pct=stats["max_pct"],
                        tree_canopy_std_pct=stats["std_pct"],
                        tree_canopy_risk_score=stats["risk_score"],
                    )
                )
                await session.execute(stmt)
                updated_count += 1

            await session.commit()
            logger.info(f"  Batch {i // batch_size + 1}: {len(batch_geoids)} tracts updated")

        except Exception as e:
            logger.error(f"Error updating batch {i // batch_size + 1}: {e}")
            await session.rollback()
            error_count += len(batch_geoids)

    logger.info(f"Update complete: {updated_count} updated, {error_count} errors")
    return {"updated": updated_count, "errors": error_count}


async def load_tree_canopy(
    geotiff_path: str,
    state_fips: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """Load NLCD Tree Canopy Cover for a state from a local GeoTIFF.

    Orchestrates the full pipeline:
    1. Load census tract geometries for the state
    2. Compute zonal statistics from raster
    3. Bulk update census_tracts table

    Args:
        geotiff_path: Path to NLCD TCC GeoTIFF file
        state_fips: Two-digit state FIPS code
        session: Async database session

    Returns:
        Stats dict with processing results
    """
    tif_path = Path(geotiff_path)
    if not tif_path.exists():
        raise TreeCanopyLoaderError(f"GeoTIFF not found: {geotiff_path}")

    logger.info(f"Loading tree canopy from {tif_path.name} for state {state_fips}")

    # Load tract geometries
    tract_geoms = await load_tract_geometries(session, state_fips)

    # Compute zonal statistics
    aggregates = aggregate_canopy_to_tracts(tif_path, tract_geoms)

    # Bulk update database
    update_stats = await bulk_update_canopy(session, aggregates)

    # Summary statistics
    if aggregates:
        mean_values = [v["mean_pct"] for v in aggregates.values()]
        risk_values = [v["risk_score"] for v in aggregates.values()]
        summary = {
            "state_fips": state_fips,
            "tracts_loaded": len(tract_geoms),
            "tracts_with_data": len(aggregates),
            "tracts_updated": update_stats["updated"],
            "errors": update_stats["errors"],
            "avg_canopy_mean": round(sum(mean_values) / len(mean_values), 1),
            "max_canopy_mean": round(max(mean_values), 1),
            "avg_risk_score": round(sum(risk_values) / len(risk_values), 1),
        }
    else:
        summary = {
            "state_fips": state_fips,
            "tracts_loaded": len(tract_geoms),
            "tracts_with_data": 0,
            "tracts_updated": 0,
            "errors": 0,
        }

    logger.info(f"Tree canopy load complete for state {state_fips}: {summary}")
    return summary
