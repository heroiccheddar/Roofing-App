"""Authentication endpoints.

Handles user registration, login, JWT token generation, and password reset.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["authentication"])

# TODO: Implement in WP 3.1
# - POST /register - create new roofer account
# - POST /login - authenticate and return JWT
# - POST /refresh - refresh JWT token
# - POST /forgot-password - initiate password reset
# - POST /reset-password - complete password reset
