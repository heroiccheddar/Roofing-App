"""Canvasser feedback endpoints.

Allows roofers to submit field observations about actual damage rates
in lead zones. Used for model calibration and continuous improvement.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/feedback", tags=["feedback"])

# TODO: Implement in WP 3.3
# - POST /feedback - submit new canvass session feedback
# - GET /feedback - list roofer's own feedback history
# - GET /feedback/{session_id} - get single session details
# - PATCH /feedback/{session_id} - update feedback (within 24h)
