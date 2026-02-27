"""Leaderboard and metrics schemas."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class LeaderboardPeriod(str, Enum):
    this_week = "this_week"
    this_month = "this_month"
    all_time = "all_time"


class LeaderboardMember(BaseModel):
    roofer_account_id: UUID
    company_name: str
    email: str
    total_pins: int = Field(..., description="Total pins dropped in period")
    not_home: int = 0
    callback: int = 0
    interested: int = 0
    inspection_set: int = 0
    contract_signed: int = 0
    not_interested: int = 0
    conversion_rate: float = Field(
        ..., description="contract_signed / total_pins (0.0 if no pins)"
    )


class LeaderboardResponse(BaseModel):
    current_user_id: UUID
    period: str
    period_start: datetime | None = Field(
        None, description="Start of the selected period (None for all_time)"
    )
    members: list[LeaderboardMember] = Field(
        ..., description="Members sorted by contract_signed desc"
    )
