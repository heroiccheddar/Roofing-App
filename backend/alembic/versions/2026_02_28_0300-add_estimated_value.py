"""Add estimated_value column to lead_pins for deal tracking.

Revision ID: add_estimated_value
Revises: add_estimates_table
Create Date: 2026-02-28 03:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "add_estimated_value"
down_revision: Union[str, None] = "add_estimates_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lead_pins",
        sa.Column("estimated_value", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lead_pins", "estimated_value")
