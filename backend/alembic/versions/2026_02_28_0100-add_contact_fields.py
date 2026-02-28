"""Add contact_name, contact_phone, contact_email columns to lead_pins.

Revision ID: add_contact_fields
Revises: add_pin_photos
Create Date: 2026-02-28 01:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "add_contact_fields"
down_revision: Union[str, None] = "add_pin_photos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lead_pins",
        sa.Column("contact_name", sa.String(), nullable=True),
    )
    op.add_column(
        "lead_pins",
        sa.Column("contact_phone", sa.String(), nullable=True),
    )
    op.add_column(
        "lead_pins",
        sa.Column("contact_email", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lead_pins", "contact_email")
    op.drop_column("lead_pins", "contact_phone")
    op.drop_column("lead_pins", "contact_name")
