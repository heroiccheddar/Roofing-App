"""Organization model for team / multi-rep support."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Organization(Base):
    """Team organization that groups multiple roofer accounts."""

    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    invite_code = Column(String(8), unique=True, nullable=False)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("roofer_accounts.id"),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    members = relationship(
        "RooferAccount",
        back_populates="organization",
        foreign_keys="RooferAccount.organization_id",
    )

    __table_args__ = (
        Index("ix_organizations_invite_code", "invite_code", unique=True),
    )
