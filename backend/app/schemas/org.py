"""Organization schemas for team / multi-rep support."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class OrgCreate(BaseModel):
    """Body for POST /org — create a new organization."""
    name: str = Field(..., min_length=1, max_length=100, description="Organization name")


class OrgJoin(BaseModel):
    """Body for POST /org/join — join by invite code."""
    invite_code: str = Field(..., min_length=8, max_length=8, description="8-character invite code")


class OrgMember(BaseModel):
    """A member in an organization."""
    id: UUID
    email: str
    company_name: str
    org_role: str


class OrgResponse(BaseModel):
    """Organization info."""
    id: UUID
    name: str
    invite_code: str
    created_by: UUID
    created_at: datetime


class OrgDetailResponse(OrgResponse):
    """Organization info with member list."""
    members: list[OrgMember]
