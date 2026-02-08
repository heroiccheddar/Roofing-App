"""Lead zone endpoints.

Retrieves scored lead zones filtered by location, score threshold, and date range.
Supports map viewport queries and list views.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/zones", tags=["lead-zones"])

# TODO: Implement in WP 3.2
# - GET /zones - list lead zones with filters (bbox, min_score, date_range)
# - GET /zones/{zone_id} - get single zone details
# - GET /zones/geojson - return zones as GeoJSON for map rendering
# - GET /zones/heatmap - return simplified heatmap data
