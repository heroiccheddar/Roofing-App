"""Internal/admin endpoints.

Administrative endpoints for monitoring, manual triggers, and system status.
Not exposed to regular users.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/internal", tags=["internal"])

# TODO: Implement in WP 3.5
# - POST /internal/trigger-ingestion - manually trigger data fetch
# - POST /internal/trigger-scoring - manually trigger scoring run
# - GET /internal/stats - system statistics (events, zones, users)
# - GET /internal/calibration - model performance metrics
