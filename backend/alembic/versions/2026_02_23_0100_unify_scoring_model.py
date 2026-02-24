"""Unify scoring model: add sub-scores, has_active_storm, partial unique index.

Adds the new unified scoring columns (roof_condition, market_quality,
risk_exposure, canvass_efficiency, storm_boost, base_score,
has_active_storm, base_scored_at), backfills existing storm/roof_age
records into the new schema, deduplicates active zones per H3 hex,
creates a partial unique index enforcing one active zone per hex, and
migrates lead_type values to 'standard'/'storm_boosted'.

Revision ID: unify_scoring_001
Revises: make_canvass_rating_nullable
Create Date: 2026-02-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "unify_scoring_001"
down_revision: Union[str, None] = "make_canvass_rating_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Add new columns to lead_zones
    # ------------------------------------------------------------------
    op.add_column("lead_zones", sa.Column("roof_condition", sa.Float(), nullable=True))
    op.add_column("lead_zones", sa.Column("market_quality", sa.Float(), nullable=True))
    op.add_column("lead_zones", sa.Column("risk_exposure", sa.Float(), nullable=True))
    op.add_column("lead_zones", sa.Column("canvass_efficiency", sa.Float(), nullable=True))
    op.add_column("lead_zones", sa.Column("storm_boost", sa.Float(), nullable=True))
    op.add_column("lead_zones", sa.Column("base_score", sa.Float(), nullable=True))
    op.add_column(
        "lead_zones",
        sa.Column(
            "has_active_storm",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "lead_zones",
        sa.Column("base_scored_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ------------------------------------------------------------------
    # 2. Backfill existing data
    # ------------------------------------------------------------------

    # Case A: active storm zones (lead_type='storm' AND active=true)
    # → mark has_active_storm=True, migrate sub-scores, rename lead_type
    op.execute(
        sa.text(
            """
            UPDATE lead_zones
            SET
                has_active_storm    = true,
                storm_boost         = damage_prob,
                base_score          = lead_quality,
                market_quality      = lead_quality,
                canvass_efficiency  = density_bonus,
                lead_type           = 'storm_boosted'
            WHERE lead_type = 'storm'
              AND active = true
            """
        )
    )

    # Case B: roof_age zones (any active status)
    # → no storm, migrate sub-scores, rename lead_type
    op.execute(
        sa.text(
            """
            UPDATE lead_zones
            SET
                has_active_storm    = false,
                storm_boost         = 0,
                base_score          = composite_score,
                market_quality      = lead_quality,
                canvass_efficiency  = density_bonus,
                lead_type           = 'standard'
            WHERE lead_type = 'roof_age'
            """
        )
    )

    # Case C: inactive storm zones (lead_type='storm' AND active=false)
    # → treat as standard (storm has since expired)
    op.execute(
        sa.text(
            """
            UPDATE lead_zones
            SET
                has_active_storm    = false,
                storm_boost         = 0,
                base_score          = lead_quality,
                market_quality      = lead_quality,
                canvass_efficiency  = density_bonus,
                lead_type           = 'standard'
            WHERE lead_type = 'storm'
              AND active = false
            """
        )
    )

    # ------------------------------------------------------------------
    # 3. Deduplicate: for H3 hexes with multiple active zones, keep the
    #    one with the highest composite_score and deactivate the rest.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY h3_index
                        ORDER BY composite_score DESC, created_at DESC
                    ) AS rn
                FROM lead_zones
                WHERE active = true
            )
            UPDATE lead_zones
            SET active = false
            FROM ranked
            WHERE lead_zones.id = ranked.id
              AND ranked.rn > 1
            """
        )
    )

    # ------------------------------------------------------------------
    # 4. Create partial unique index: one active zone per H3 hex
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX ix_lead_zones_h3_active_unique
            ON lead_zones (h3_index)
            WHERE active = true
            """
        )
    )

    # ------------------------------------------------------------------
    # 5. Create composite index on (has_active_storm, active)
    # ------------------------------------------------------------------
    op.create_index(
        "ix_lead_zones_has_active_storm",
        "lead_zones",
        ["has_active_storm", "active"],
    )

    # ------------------------------------------------------------------
    # 6. Change lead_type server default to 'standard'
    # ------------------------------------------------------------------
    op.alter_column(
        "lead_zones",
        "lead_type",
        existing_type=sa.String(),
        existing_nullable=False,
        server_default=sa.text("'standard'"),
    )


def downgrade() -> None:
    # Restore lead_type server default to 'storm'
    op.alter_column(
        "lead_zones",
        "lead_type",
        existing_type=sa.String(),
        existing_nullable=False,
        server_default=sa.text("'storm'"),
    )

    # Drop indexes created in upgrade
    op.drop_index("ix_lead_zones_has_active_storm", table_name="lead_zones")
    op.execute(sa.text("DROP INDEX IF EXISTS ix_lead_zones_h3_active_unique"))

    # NOTE: Data backfill is not reversed — rolling back lead_type values
    # and has_active_storm/storm_boost etc. would require knowing the original
    # per-row state, which is not safely reconstructible. A full data restore
    # from backup is required if downgrade is applied to a production database.

    # Drop new columns
    op.drop_column("lead_zones", "base_scored_at")
    op.drop_column("lead_zones", "has_active_storm")
    op.drop_column("lead_zones", "base_score")
    op.drop_column("lead_zones", "storm_boost")
    op.drop_column("lead_zones", "canvass_efficiency")
    op.drop_column("lead_zones", "risk_exposure")
    op.drop_column("lead_zones", "market_quality")
    op.drop_column("lead_zones", "roof_condition")
