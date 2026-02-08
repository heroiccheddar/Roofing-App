"""Load US Census data for specified states.

Fetches census tract boundaries and ACS demographic data from Census Bureau API.
Loads into the database for demographic enrichment of lead zones.

Usage:
    python scripts/load_census_data.py --states TX OK KS
"""

# TODO: Implement in WP 1.3
# - Parse command line arguments for state FIPS codes
# - Call census_loader ingestion module
# - Bulk insert census tracts with geometries
# - Handle errors and provide progress reporting
# - Support incremental updates (skip existing tracts)
pass
