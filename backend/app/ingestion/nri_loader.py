"""FEMA National Risk Index (NRI) data loader.

Downloads tract-level risk scores for hail, strong wind, and tornado hazards.
Updates census_tracts table with risk metrics that enhance lead scoring.

Data source: https://hazards.fema.gov/nri/data-resources
"""

import logging
import tempfile
import zipfile
from pathlib import Path

import httpx
import pandas as pd
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

NRI_CSV_URL = "https://www.fema.gov/about/reports-and-data/openfema/nri/v120/NRI_Table_CensusTracts.zip"

# Map NRI CSV columns to our database columns
NRI_COLUMN_MAP = {
    "TRACTFIPS": "geoid",
    "HAIL_AFREQ": "nri_hail_afreq",
    "HAIL_EXPB": "nri_hail_expb",
    "HAIL_EALT": "nri_hail_ealt",
    "HAIL_RISKR": "nri_hail_riskr",
    "SWND_AFREQ": "nri_swnd_afreq",
    "SWND_EXPB": "nri_swnd_expb",
    "SWND_EALT": "nri_swnd_ealt",
    "SWND_RISKR": "nri_swnd_riskr",
    "TRND_AFREQ": "nri_trnd_afreq",
    "TRND_EXPB": "nri_trnd_expb",
    "TRND_EALT": "nri_trnd_ealt",
    "TRND_RISKR": "nri_trnd_riskr",
}

# Target state FIPS codes (TX, OK, KS, CO, NE, GA)
TARGET_STATE_FIPS = {"48", "40", "20", "08", "31", "13"}

# NRI columns that are numeric (vs string for risk ratings)
NUMERIC_NRI_COLS = [
    "HAIL_AFREQ", "HAIL_EXPB", "HAIL_EALT",
    "SWND_AFREQ", "SWND_EXPB", "SWND_EALT",
    "TRND_AFREQ", "TRND_EXPB", "TRND_EALT",
]


async def download_nri_csv() -> Path:
    """Download the NRI ZIP file and extract the CSV.

    The NRI data is distributed as a ZIP (~40MB compressed, ~400MB CSV inside).
    Uses streaming download to avoid loading the entire file into memory.

    Returns:
        Path to the extracted CSV file (in a temp directory)

    Raises:
        httpx.HTTPError: If download fails
    """
    logger.info(f"Downloading NRI ZIP from {NRI_CSV_URL}")

    # Create temp directory to hold zip and extracted CSV
    tmpdir = tempfile.mkdtemp(prefix="nri_")
    tmpdir_path = Path(tmpdir)
    zip_path = tmpdir_path / "NRI_Table_CensusTracts.zip"

    try:
        async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as client:
            async with client.stream("GET", NRI_CSV_URL) as response:
                response.raise_for_status()

                total_bytes = 0
                chunk_size = 1024 * 1024  # 1MB chunks

                with open(zip_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                        f.write(chunk)
                        total_bytes += len(chunk)

                        # Log progress every 10MB
                        if total_bytes % (10 * 1024 * 1024) < chunk_size:
                            logger.info(f"  Downloaded {total_bytes / (1024 * 1024):.1f} MB")

        logger.info(f"Download complete: {total_bytes / (1024 * 1024):.1f} MB")

        # Extract ZIP
        logger.info("Extracting NRI ZIP file...")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmpdir_path)

        # Remove ZIP to save disk space
        zip_path.unlink()

        # Find the actual data CSV (not the data dictionary)
        csv_files = list(tmpdir_path.glob("*.csv"))
        if not csv_files:
            raise FileNotFoundError("No CSV file found in NRI ZIP archive")

        # Prefer files with "CensusTracts" or "Table" in the name, otherwise pick the largest
        csv_path = None
        for f in csv_files:
            if "CensusTracts" in f.name or "Table" in f.name:
                csv_path = f
                break
        if csv_path is None:
            # Fall back to the largest CSV file
            csv_path = max(csv_files, key=lambda f: f.stat().st_size)
        logger.info(f"Extracted CSV: {csv_path.name} ({csv_path.stat().st_size / (1024 * 1024):.1f} MB)")
        return csv_path

    except Exception as e:
        # Clean up on error
        import shutil
        if tmpdir_path.exists():
            shutil.rmtree(tmpdir_path)
        raise


def parse_nri_dataframe(csv_path: Path) -> pd.DataFrame:
    """Parse NRI CSV into a filtered DataFrame ready for database update.

    Args:
        csv_path: Path to the downloaded NRI CSV file

    Returns:
        DataFrame with columns renamed to match database schema,
        filtered to target states only
    """
    logger.info(f"Parsing NRI CSV from {csv_path}")

    # Only load the columns we need
    columns_to_load = ["TRACTFIPS", "STCOFIPS"] + list(NRI_COLUMN_MAP.keys())
    columns_to_load = list(set(columns_to_load))  # Remove duplicates

    # Read CSV with dtype hints to handle mixed types
    df = pd.read_csv(
        csv_path,
        usecols=columns_to_load,
        dtype={
            "TRACTFIPS": str,
            "STCOFIPS": str,
            # Risk ratings are strings
            "HAIL_RISKR": str,
            "SWND_RISKR": str,
            "TRND_RISKR": str,
        },
        low_memory=False,
    )

    logger.info(f"Loaded {len(df)} total tracts from CSV")

    # Filter to target states using first 2 digits of TRACTFIPS
    df["state_fips"] = df["TRACTFIPS"].str[:2]
    df_filtered = df[df["state_fips"].isin(TARGET_STATE_FIPS)].copy()

    logger.info(f"Filtered to {len(df_filtered)} tracts in target states")

    # Convert numeric columns, coercing errors to NaN
    for col in NUMERIC_NRI_COLS:
        if col in df_filtered.columns:
            df_filtered[col] = pd.to_numeric(df_filtered[col], errors='coerce')

    # Rename columns to match our database schema
    # Only rename columns that exist in the DataFrame
    rename_map = {k: v for k, v in NRI_COLUMN_MAP.items() if k in df_filtered.columns}
    df_filtered = df_filtered.rename(columns=rename_map)

    # Drop temporary columns
    df_filtered = df_filtered.drop(columns=["state_fips"], errors='ignore')
    if "STCOFIPS" in df_filtered.columns:
        df_filtered = df_filtered.drop(columns=["STCOFIPS"])

    logger.info(f"Parsed {len(df_filtered)} tracts ready for database update")

    return df_filtered


async def bulk_update_nri(
    session: AsyncSession,
    df: pd.DataFrame,
    batch_size: int = 500,
) -> dict:
    """Bulk update census tracts with NRI data.

    Issues UPDATE statements for each tract, setting only the NRI columns.
    Tracts not found in the database are skipped.

    Args:
        session: Async database session
        df: DataFrame with NRI data (must have 'geoid' column)
        batch_size: Number of rows to update per batch

    Returns:
        Dict with counts:
        - updated: Number of tracts successfully updated
        - skipped: Number of tracts not found in database
        - errors: Number of rows that failed to update
    """
    if df.empty:
        return {"updated": 0, "skipped": 0, "errors": 0}

    logger.info(f"Starting bulk update of {len(df)} tracts")

    updated = 0
    skipped = 0
    errors = 0

    # Get the list of NRI database columns (exclude geoid which is the WHERE clause)
    nri_db_cols = [col for col in NRI_COLUMN_MAP.values() if col != "geoid"]

    # Process in batches
    total_batches = (len(df) + batch_size - 1) // batch_size

    for batch_idx in range(0, len(df), batch_size):
        batch_df = df.iloc[batch_idx:batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1

        try:
            # Convert batch to list of dicts for easier processing
            batch_records = batch_df.to_dict('records')

            for record in batch_records:
                geoid = record.get('geoid')
                if not geoid:
                    errors += 1
                    continue

                # Build update dict with only NRI columns
                update_values = {}
                for db_col in nri_db_cols:
                    if db_col in record:
                        value = record[db_col]
                        # Convert pandas NA/NaN to None for database
                        if pd.isna(value):
                            update_values[db_col] = None
                        else:
                            update_values[db_col] = value

                if not update_values:
                    skipped += 1
                    continue

                # Execute UPDATE statement
                stmt = (
                    update(CensusTract)
                    .where(CensusTract.geoid == geoid)
                    .values(**update_values)
                )

                result = await session.execute(stmt)

                if result.rowcount > 0:
                    updated += 1
                else:
                    # No rows updated means geoid not found
                    skipped += 1

            # Commit after each batch
            await session.commit()
            logger.info(
                f"  Processed batch {batch_num}/{total_batches} "
                f"({updated} updated, {skipped} skipped, {errors} errors)"
            )

        except Exception as e:
            logger.error(f"Error processing batch {batch_num}: {e}", exc_info=True)
            await session.rollback()
            errors += len(batch_records)

    logger.info(
        f"Bulk update complete: {updated} updated, "
        f"{skipped} skipped, {errors} errors"
    )

    return {
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


async def load_nri_data(session: AsyncSession) -> dict:
    """Load FEMA NRI data into census_tracts table.

    Orchestrates the full process:
    1. Download NRI CSV file
    2. Parse and filter to target states
    3. Bulk update census_tracts with NRI metrics

    Args:
        session: Async database session

    Returns:
        Dict with counts:
        - downloaded: Number of total tracts in CSV
        - filtered_tracts: Number of tracts in target states
        - updated: Number of tracts successfully updated
        - skipped: Number of tracts not found in database
        - errors: Number of rows that failed to update

    Example:
        >>> result = await load_nri_data(session)
        >>> print(f"Updated {result['updated']} tracts with NRI data")
    """
    csv_path = None

    try:
        # Download and extract CSV from ZIP
        csv_path = await download_nri_csv()

        # Parse and filter
        df = parse_nri_dataframe(csv_path)

        # Track stats
        stats = {
            "downloaded": len(df),  # Already filtered at this point
            "filtered_tracts": len(df),
        }

        # Bulk update database
        update_stats = await bulk_update_nri(session, df)
        stats.update(update_stats)

        logger.info(f"NRI data load complete: {stats}")
        return stats

    finally:
        # Clean up temporary directory
        if csv_path and csv_path.parent.exists():
            try:
                import shutil
                shutil.rmtree(csv_path.parent)
                logger.info(f"Cleaned up temporary directory: {csv_path.parent}")
            except Exception as e:
                logger.warning(f"Failed to delete temporary directory {csv_path.parent}: {e}")
