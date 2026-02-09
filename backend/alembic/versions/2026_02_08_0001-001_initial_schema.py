"""Initial schema — PostGIS extension + 7 tables.

Revision ID: 001
Revises:
Create Date: 2026-02-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable PostGIS extension (Neon supports this)
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # ── storm_events ──
    op.create_table(
        "storm_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("location",
                  geoalchemy2.Geometry(geometry_type="POINT", srid=4326),
                  nullable=False),
        sa.Column("warning_polygon",
                  geoalchemy2.Geometry(geometry_type="POLYGON", srid=4326),
                  nullable=True),
        sa.Column("hail_diameter", sa.Float(), nullable=True),
        sa.Column("wind_speed", sa.Float(), nullable=True),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nws_event_id", sa.String(), nullable=True, unique=True),
        sa.Column("spc_report_id", sa.String(), nullable=True),
        sa.Column("swdi_cell_id", sa.String(), nullable=True),
        sa.Column("radar_confidence", sa.Float(), nullable=True),
        sa.Column("corroborated", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("corroboration_sources", postgresql.JSONB(), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        sa.Column("scored", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_storm_events_location", "storm_events",
                    ["location"], postgresql_using="gist")
    op.create_index("ix_storm_events_warning_polygon", "storm_events",
                    ["warning_polygon"], postgresql_using="gist")
    op.create_index("ix_storm_events_event_timestamp", "storm_events",
                    ["event_timestamp"], postgresql_using="brin")
    op.create_index("ix_storm_events_source", "storm_events", ["source"])
    op.create_index("ix_storm_events_scored", "storm_events", ["scored"])

    # ── census_tracts ──
    op.create_table(
        "census_tracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("geoid", sa.String(), nullable=False, unique=True),
        sa.Column("state_fips", sa.String(), nullable=False),
        sa.Column("county_fips", sa.String(), nullable=False),
        sa.Column("tract_code", sa.String(), nullable=False),
        sa.Column("geometry",
                  geoalchemy2.Geometry(geometry_type="MULTIPOLYGON", srid=4326),
                  nullable=False),
        sa.Column("owner_occupied_pct", sa.Float(), nullable=True),
        sa.Column("median_year_built", sa.Integer(), nullable=True),
        sa.Column("median_home_value", sa.Float(), nullable=True),
        sa.Column("population", sa.Integer(), nullable=True),
        sa.Column("housing_units", sa.Integer(), nullable=True),
        sa.Column("area_sq_km", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_census_tracts_geometry", "census_tracts",
                    ["geometry"], postgresql_using="gist")
    op.create_index("ix_census_tracts_state_fips", "census_tracts",
                    ["state_fips"])
    op.create_index("ix_census_tracts_state_county", "census_tracts",
                    ["state_fips", "county_fips"])

    # ── roofer_accounts ──
    op.create_table(
        "roofer_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("company_name", sa.String(), nullable=False),
        sa.Column("phone_number", sa.String(), nullable=True),
        sa.Column("service_area",
                  geoalchemy2.Geometry(geometry_type="POLYGON", srid=4326),
                  nullable=False),
        sa.Column("alert_preferences", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("subscription_tier", sa.String(), nullable=False,
                  server_default=sa.text("'free'")),
        sa.Column("is_admin", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_roofer_accounts_service_area", "roofer_accounts",
                    ["service_area"], postgresql_using="gist")
    op.create_index("ix_roofer_accounts_subscription_tier", "roofer_accounts",
                    ["subscription_tier"])
    op.create_index("ix_roofer_accounts_is_active", "roofer_accounts",
                    ["is_active"])

    # ── lead_zones ──
    op.create_table(
        "lead_zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("boundary",
                  geoalchemy2.Geometry(geometry_type="POLYGON", srid=4326),
                  nullable=False),
        sa.Column("centroid",
                  geoalchemy2.Geometry(geometry_type="POINT", srid=4326),
                  nullable=False),
        sa.Column("h3_index", sa.String(), nullable=False),
        sa.Column("composite_score", sa.Float(), nullable=False),
        sa.Column("damage_prob", sa.Float(), nullable=False),
        sa.Column("lead_quality", sa.Float(), nullable=False),
        sa.Column("density_bonus", sa.Float(), nullable=False),
        sa.Column("predicted_conversion_rate", sa.Float(), nullable=True),
        sa.Column("score_band", sa.String(), nullable=False),
        sa.Column("score_weights_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False,
                  server_default=sa.text("1")),
        sa.Column("max_hail_diameter", sa.Float(), nullable=True),
        sa.Column("max_wind_speed", sa.Float(), nullable=True),
        sa.Column("primary_event_timestamp", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lead_zones_boundary", "lead_zones",
                    ["boundary"], postgresql_using="gist")
    op.create_index("ix_lead_zones_centroid", "lead_zones",
                    ["centroid"], postgresql_using="gist")
    op.create_index("ix_lead_zones_created_at", "lead_zones",
                    ["created_at"], postgresql_using="brin")
    op.create_index("ix_lead_zones_score_expires", "lead_zones",
                    ["composite_score", "expires_at"])
    op.create_index("ix_lead_zones_h3_index", "lead_zones", ["h3_index"])
    op.create_index("ix_lead_zones_score_band", "lead_zones", ["score_band"])
    op.create_index("ix_lead_zones_active", "lead_zones", ["active"])
    op.create_index("ix_lead_zones_expires_at", "lead_zones", ["expires_at"])

    # ── canvass_sessions ──
    op.create_table(
        "canvass_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("lead_zone_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lead_zones.id"), nullable=False),
        sa.Column("roofer_account_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("roofer_accounts.id"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("doors_knocked", sa.Integer(), nullable=True),
        sa.Column("doors_answered", sa.Integer(), nullable=True),
        sa.Column("visible_damage_count", sa.Integer(), nullable=True),
        sa.Column("homeowner_interested", sa.Integer(), nullable=True),
        sa.Column("inspections_scheduled", sa.Integer(), nullable=True),
        sa.Column("contracts_signed", sa.Integer(), nullable=True),
        sa.Column("estimated_revenue", sa.Float(), nullable=True),
        sa.Column("roof_type", sa.String(), nullable=True),
        sa.Column("competitor_presence", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("zone_score_at_time", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_canvass_sessions_lead_zone_id", "canvass_sessions",
                    ["lead_zone_id"])
    op.create_index("ix_canvass_sessions_roofer_account_id", "canvass_sessions",
                    ["roofer_account_id"])
    op.create_index("ix_canvass_sessions_created_at", "canvass_sessions",
                    ["created_at"])
    op.create_index("ix_canvass_sessions_rating", "canvass_sessions",
                    ["rating"])

    # ── alert_log ──
    op.create_table(
        "alert_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("roofer_account_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("roofer_accounts.id"), nullable=False),
        sa.Column("lead_zone_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lead_zones.id"), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acted_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_alert_log_roofer_account_id", "alert_log",
                    ["roofer_account_id"])
    op.create_index("ix_alert_log_lead_zone_id", "alert_log",
                    ["lead_zone_id"])
    op.create_index("ix_alert_log_dedup", "alert_log",
                    ["roofer_account_id", "lead_zone_id", "channel"])
    op.create_index("ix_alert_log_sent_at", "alert_log", ["sent_at"])
    op.create_index("ix_alert_log_channel", "alert_log", ["channel"])

    # ── model_calibration ──
    op.create_table(
        "model_calibration",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=False),
        sa.Column("hail_size_bucket", sa.String(), nullable=False),
        sa.Column("avg_predicted_conversion", sa.Float(), nullable=False),
        sa.Column("avg_actual_conversion", sa.Float(), nullable=False),
        sa.Column("prediction_bias", sa.Float(), nullable=False),
        sa.Column("avg_competitor_saturation", sa.Float(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_model_calibration_lookup", "model_calibration",
                    ["model_version", "region", "hail_size_bucket"])
    op.create_index("ix_model_calibration_period_end", "model_calibration",
                    ["period_end"])
    op.create_index("ix_model_calibration_computed_at", "model_calibration",
                    ["computed_at"])


def downgrade() -> None:
    op.drop_table("alert_log")
    op.drop_table("canvass_sessions")
    op.drop_table("model_calibration")
    op.drop_table("lead_zones")
    op.drop_table("roofer_accounts")
    op.drop_table("census_tracts")
    op.drop_table("storm_events")
    op.execute("DROP EXTENSION IF EXISTS postgis")
