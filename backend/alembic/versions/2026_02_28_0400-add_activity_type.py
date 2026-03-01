"""Add activity_type column to pin_activities for Communication Log feature.

Existing rows receive 'disposition_change' via server_default — no data
migration is required. User-created activities (call, text, email, visit,
note) set this field explicitly from the request body.

Revision ID: add_activity_type
Revises: add_estimated_value
Create Date: 2026-02-28 04:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "add_activity_type"
down_revision: Union[str, None] = "add_estimated_value"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pin_activities",
        sa.Column(
            "activity_type",
            sa.String(),
            server_default="disposition_change",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("pin_activities", "activity_type")
