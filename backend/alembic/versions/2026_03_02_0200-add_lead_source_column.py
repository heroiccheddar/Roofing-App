"""Add lead_source column to lead_pins table.

Stores how a lead was acquired (door_knock, referral, website,
storm_canvass, other). Nullable so existing pins are unaffected.

Revision ID: add_lead_source_column
Revises: add_roof_data_columns
Create Date: 2026-03-02 02:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "add_lead_source_column"
down_revision = "add_roof_data_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lead_pins", sa.Column("lead_source", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("lead_pins", "lead_source")
