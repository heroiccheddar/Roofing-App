"""Alert schemas for notification logs and history.

Tracks sent alerts (email/SMS/websocket) and engagement metrics.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class AlertLogResponse(BaseModel):
    """Response schema for individual alert log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Alert log ID")
    lead_zone_id: UUID = Field(..., description="Zone ID this alert is for")
    channel: str = Field(..., description="Alert channel: 'sms', 'email', 'websocket'")

    # Delivery tracking
    sent_at: datetime = Field(..., description="When alert was sent")
    opened_at: datetime | None = Field(None, description="When roofer opened alert")
    acted_on: datetime | None = Field(
        None, description="When roofer opened zone detail from alert"
    )

    # Zone context at time of alert
    zone_score: float | None = Field(None, description="Zone score when alert was sent")
    zone_h3_index: str | None = Field(None, description="Zone H3 index")


class AlertHistoryResponse(BaseModel):
    """Paginated response for alert history."""

    alerts: list[AlertLogResponse] = Field(
        default_factory=list, description="List of alert log entries"
    )
    total: int = Field(..., description="Total alerts for this roofer")
