"""Add callback_date column to lead_pins table.

Revision ID: a3f8c21d904e
Revises: add_lead_pins
Create Date: 2026-02-26 03:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3f8c21d904e"
down_revision: Union[str, None] = "add_lead_pins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lead_pins",
        sa.Column("callback_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_lead_pins_callback_date",
        "lead_pins",
        ["callback_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_lead_pins_callback_date", table_name="lead_pins")
    op.drop_column("lead_pins", "callback_date")
