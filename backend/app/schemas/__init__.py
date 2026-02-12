"""Pydantic schemas for API request/response models.

This module re-exports all schema classes for convenient importing.
Schemas are independent of SQLAlchemy models and define the API contract.
"""

# Common schemas
from app.schemas.common import PaginationParams, ErrorResponse

# Authentication
from app.schemas.auth import AuthRegister, AuthLogin, TokenResponse

# Account management
from app.schemas.account import (
    ServiceAreaUpdate,
    AlertPreferences,
    QuietHours,
    AccountResponse,
)

# Lead zones
from app.schemas.zones import (
    ZoneListParams,
    ZoneResponse,
    ZoneDetailResponse,
    StormEventBrief,
    ZoneListResponse,
    ZoneGeoJSONFeature,
    ZoneGeoJSONResponse,
    GeoJSONGeometry,
)

# Zone feedback (POC)
from app.schemas.feedback import (
    ZoneFeedbackCreate,
    ZoneFeedbackResponse,
    ZoneFeedbackListResponse,
)

# Alerts
from app.schemas.alerts import AlertLogResponse, AlertHistoryResponse

# Internal admin
from app.schemas.internal import (
    CalibrationEntry,
    CalibrationReport,
    WeightChange,
    WeightProposal,
    ModelDeployRequest,
    ModelDeployResponse,
)

__all__ = [
    # Common
    "PaginationParams",
    "ErrorResponse",
    # Auth
    "AuthRegister",
    "AuthLogin",
    "TokenResponse",
    # Account
    "ServiceAreaUpdate",
    "AlertPreferences",
    "QuietHours",
    "AccountResponse",
    # Zones
    "ZoneListParams",
    "ZoneResponse",
    "ZoneDetailResponse",
    "StormEventBrief",
    "ZoneListResponse",
    "ZoneGeoJSONFeature",
    "ZoneGeoJSONResponse",
    "GeoJSONGeometry",
    # Zone feedback
    "ZoneFeedbackCreate",
    "ZoneFeedbackResponse",
    "ZoneFeedbackListResponse",
    # Alerts
    "AlertLogResponse",
    "AlertHistoryResponse",
    # Internal
    "CalibrationEntry",
    "CalibrationReport",
    "WeightChange",
    "WeightProposal",
    "ModelDeployRequest",
    "ModelDeployResponse",
]
