"""Initial schema — all application tables.

Creates: users, water_quality_readings, fish_growth_records,
         feeding_records, alerts.

Note: TimescaleDB hypertables for water_quality_readings, fish_growth_records,
and feeding_records are created separately in infra/postgres/init.sql which
runs at container boot, before migrations. Alembic manages schema-level
changes; TimescaleDB partitioning is infrastructure-level.

Revision ID: 0001
Revises:
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
    )
    return {row[0] for row in rows}


def upgrade() -> None:
    existing = _existing_tables()

    # ── users ──────────────────────────────────────────────────────────────────
    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("username", sa.String(64), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("hashed_password", sa.String(255), nullable=False),
            sa.Column("full_name", sa.String(128), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
    op.create_index("ix_users_id", "users", ["id"], if_not_exists=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True, if_not_exists=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True, if_not_exists=True)

    # ── water_quality_readings ─────────────────────────────────────────────────
    if "water_quality_readings" not in existing:
        op.create_table(
            "water_quality_readings",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("tank_id", sa.String(50), nullable=False, index=True),
            sa.Column("measured_at", sa.DateTime(), nullable=False, index=True),
            sa.Column("temperature_c", sa.Float(), nullable=True),
            sa.Column("ph", sa.Float(), nullable=True),
            sa.Column("dissolved_oxygen_mgl", sa.Float(), nullable=True),
            sa.Column("turbidity_ntu", sa.Float(), nullable=True),
            sa.Column("salinity_ppt", sa.Float(), nullable=True),
            sa.Column("ammonia_ppm", sa.Float(), nullable=True),
            sa.Column("nitrite_ppm", sa.Float(), nullable=True),
            sa.Column("nitrate_ppm", sa.Float(), nullable=True),
            sa.Column("ammonia_confidence", sa.Float(), nullable=True),
            sa.Column("nitrite_confidence", sa.Float(), nullable=True),
            sa.Column("source", sa.String(20), nullable=False, server_default="sensor"),
        )
    op.create_index(
        "ix_wq_tank_time", "water_quality_readings", ["tank_id", "measured_at"],
        if_not_exists=True,
    )

    # ── fish_growth_records ────────────────────────────────────────────────────
    if "fish_growth_records" not in existing:
        op.create_table(
            "fish_growth_records",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("tank_id", sa.String(50), nullable=False, index=True),
            sa.Column("measured_at", sa.DateTime(), nullable=False, index=True),
            sa.Column("avg_length_cm", sa.Float(), nullable=True),
            sa.Column("avg_weight_g", sa.Float(), nullable=True),
            sa.Column("fish_count", sa.Integer(), nullable=True),
            sa.Column("biomass_kg", sa.Float(), nullable=True),
            sa.Column("daily_growth_rate_pct", sa.Float(), nullable=True),
            sa.Column("feed_conversion_ratio", sa.Float(), nullable=True),
            sa.Column("model_version", sa.String(50), nullable=True),
            sa.Column("inference_confidence", sa.Float(), nullable=True),
            sa.Column("frame_count_analyzed", sa.Integer(), nullable=True),
        )
    op.create_index(
        "ix_fg_tank_time", "fish_growth_records", ["tank_id", "measured_at"],
        if_not_exists=True,
    )

    # ── feeding_records ────────────────────────────────────────────────────────
    if "feeding_records" not in existing:
        op.create_table(
            "feeding_records",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("tank_id", sa.String(50), nullable=False, index=True),
            sa.Column("started_at", sa.DateTime(), nullable=False, index=True),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("commanded_amount_kg", sa.Float(), nullable=True),
            sa.Column("actual_amount_kg", sa.Float(), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("activity_score", sa.Float(), nullable=True),
            sa.Column("recommended_amount_kg", sa.Float(), nullable=True),
            sa.Column("feed_waste_estimate_pct", sa.Float(), nullable=True),
            sa.Column("trigger_source", sa.String(20), nullable=False, server_default="ai"),
            sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("is_emergency_stopped", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("model_version", sa.String(50), nullable=True),
        )
    op.create_index(
        "ix_feed_tank_time", "feeding_records", ["tank_id", "started_at"],
        if_not_exists=True,
    )

    # ── alerts ─────────────────────────────────────────────────────────────────
    if "alerts" not in existing:
        op.create_table(
            "alerts",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("tank_id", sa.String(50), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("severity", sa.String(20), nullable=False),
            sa.Column("category", sa.String(50), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("metric_name", sa.String(100), nullable=True),
            sa.Column("metric_value", sa.String(50), nullable=True),
            sa.Column("threshold_value", sa.String(50), nullable=True),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default="true", index=True
            ),
            sa.Column("resolution_notes", sa.Text(), nullable=True),
            sa.Column("resolved_by", sa.String(100), nullable=True),
            sa.Column("source", sa.String(50), nullable=False, server_default="system"),
        )
    op.create_index(
        "ix_alert_tank_active", "alerts", ["tank_id", "is_active"], if_not_exists=True
    )
    op.create_index("ix_alert_time", "alerts", ["created_at"], if_not_exists=True)


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("feeding_records")
    op.drop_table("fish_growth_records")
    op.drop_table("water_quality_readings")
    op.drop_table("users")
