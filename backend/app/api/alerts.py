"""Alert management endpoints.

Manages roofer alert preferences and retrieves alert history.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/alerts", tags=["alerts"])

# TODO: Implement in WP 3.4
# - GET /alerts - list roofer's received alerts
# - PATCH /alerts/preferences - update email/SMS preferences
# - GET /alerts/preferences - get current alert settings
