"""Add last_canvassed_at to lead_zones for canvass freshness tracking.

last_canvassed_at is updated by the canvass session and feedback
submission workflows whenever a roofer records activity in a zone.
The recommendation engine uses it to compute a freshness sub-score that
surfaces zones which have gone the longest without a canvasser visit.

Revision ID: add_last_canvassed_at
Revises: unify_scoring_001
Create Date: 2026-02-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "add_last_canvassed_at"
down_revision: Union[str, None] = "unify_scoring_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the staleness-tracking column
    op.add_column(
        "lead_zones",
        sa.Column("last_canvassed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Index to support ORDER BY last_canvassed_at queries in the recommendation
    # engine (e.g., finding zones not canvassed recently)
    op.create_index(
        "ix_lead_zones_last_canvassed_at",
        "lead_zones",
        ["last_canvassed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_lead_zones_last_canvassed_at", table_name="lead_zones")
    op.drop_column("lead_zones", "last_canvassed_at")
