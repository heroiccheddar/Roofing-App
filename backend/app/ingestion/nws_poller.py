"""NWS Storm Events Database poller.

Fetches severe weather reports from the National Weather Service
Storm Events Database API. Polls for new events on a scheduled basis
and stores them as StormEvent records.

API Documentation: https://www.ncdc.noaa.gov/stormevents/
"""

# TODO: Implement in WP 1.1
# - async fetch_recent_events(since: datetime) -> list[dict]
# - parse and validate NWS CSV/JSON format
# - convert to StormEvent model instances
# - handle pagination and rate limiting
# - filter for hail >= 1", tornado, wind >= 60mph
pass
