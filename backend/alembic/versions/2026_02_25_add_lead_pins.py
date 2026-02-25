"""Add lead_pins and pin_activities tables.

Revision ID: add_lead_pins
Revises: add_neighborhood_name
Create Date: 2026-02-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "add_lead_pins"
down_revision: Union[str, None] = "add_neighborhood_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # lead_pins — one row per pinned address per roofer
    # -----------------------------------------------------------------------
    op.create_table(
        "lead_pins",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "roofer_account_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("roofer_accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "property_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("properties.id"),
            nullable=True,
        ),
        sa.Column(
            "lead_zone_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("lead_zones.id"),
            nullable=True,
        ),
        sa.Column(
            "location",
            Geometry(geometry_type="POINT", srid=4326),
            nullable=False,
        ),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("disposition", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # GIST index on location for spatial bbox queries
    op.create_index(
        "ix_lead_pins_location",
        "lead_pins",
        ["location"],
        postgresql_using="gist",
    )

    # B-tree index on roofer_account_id — the primary filter on every query
    op.create_index(
        "ix_lead_pins_roofer_account_id",
        "lead_pins",
        ["roofer_account_id"],
    )

    # B-tree index on disposition for status filtering
    op.create_index(
        "ix_lead_pins_disposition",
        "lead_pins",
        ["disposition"],
    )

    # BRIN index on created_at for time-range queries (append-only insert pattern)
    op.create_index(
        "ix_lead_pins_created_at",
        "lead_pins",
        ["created_at"],
        postgresql_using="brin",
    )

    # -----------------------------------------------------------------------
    # pin_activities — one row per interaction / status change
    # -----------------------------------------------------------------------
    op.create_table(
        "pin_activities",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "lead_pin_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("lead_pins.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "roofer_account_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("roofer_accounts.id"),
            nullable=False,
        ),
        sa.Column("disposition", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Composite B-tree index for timeline queries ordered by time
    op.create_index(
        "ix_pin_activities_pin_created",
        "pin_activities",
        ["lead_pin_id", "created_at"],
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_index("ix_pin_activities_pin_created", table_name="pin_activities")
    op.drop_table("pin_activities")

    op.drop_index("ix_lead_pins_created_at", table_name="lead_pins")
    op.drop_index("ix_lead_pins_disposition", table_name="lead_pins")
    op.drop_index("ix_lead_pins_roofer_account_id", table_name="lead_pins")
    op.drop_index("ix_lead_pins_location", table_name="lead_pins")
    op.drop_table("lead_pins")
