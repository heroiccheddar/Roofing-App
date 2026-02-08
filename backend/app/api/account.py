"""Roofer account management endpoints.

Handles profile updates, service area configuration, and subscription management.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/account", tags=["account"])

# TODO: Implement in WP 3.4
# - GET /account/profile - get current user profile
# - PATCH /account/profile - update profile (company name, contact info)
# - PUT /account/service-area - update service area polygon
# - GET /account/subscription - get subscription status
