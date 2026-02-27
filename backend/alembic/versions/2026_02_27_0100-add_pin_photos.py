"""Add pin_photos table for photo storage on lead pins.

Revision ID: add_pin_photos
Revises: add_organizations
Create Date: 2026-02-27 01:00:00
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "add_pin_photos"
down_revision: Union[str, None] = "add_organizations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pin_photos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_pin_id", UUID(as_uuid=True),
                   sa.ForeignKey("lead_pins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("roofer_account_id", UUID(as_uuid=True),
                   sa.ForeignKey("roofer_accounts.id"), nullable=False),
        sa.Column("s3_key", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pin_photos_lead_pin_id", "pin_photos", ["lead_pin_id"])


def downgrade() -> None:
    op.drop_index("ix_pin_photos_lead_pin_id", table_name="pin_photos")
    op.drop_table("pin_photos")
