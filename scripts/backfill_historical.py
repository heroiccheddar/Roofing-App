"""Backfill historical storm data.

Fetches storm events from NWS database for a specified date range
and loads them into the database. Used for initial data population
or filling gaps in coverage.

Usage:
    python scripts/backfill_historical.py --start 2023-01-01 --end 2024-12-31
"""

# TODO: Implement in WP 1.4
# - Parse date range arguments
# - Call NWS poller with historical date range
# - Batch insert storm events
# - Handle rate limiting and retries
# - Skip existing events (check by unique identifiers)
# - Report statistics on events loaded
pass
