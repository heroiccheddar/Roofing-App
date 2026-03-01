"""Add estimates table for the Estimate Builder feature.

Revision ID: add_estimates_table
Revises: add_contact_fields
Create Date: 2026-02-28 02:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "add_estimates_table"
down_revision: Union[str, None] = "add_contact_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "estimates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "lead_pin_id",
            UUID(as_uuid=True),
            sa.ForeignKey("lead_pins.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "roofer_account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("roofer_accounts.id"),
            nullable=False,
        ),
        sa.Column("line_items", JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "subtotal",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "tax_rate",
            sa.Numeric(5, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_estimates_lead_pin_id", "estimates", ["lead_pin_id"])
    op.create_index(
        "ix_estimates_roofer_account_id", "estimates", ["roofer_account_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_estimates_roofer_account_id", table_name="estimates")
    op.drop_index("ix_estimates_lead_pin_id", table_name="estimates")
    op.drop_table("estimates")
