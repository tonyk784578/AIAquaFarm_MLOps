-- AIAquafarm PostgreSQL + TimescaleDB initialisation script
-- Runs once on first container start via docker-entrypoint-initdb.d

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Create MLflow database
CREATE DATABASE aquafarm_mlflow;

-- ── TimescaleDB Hypertables ────────────────────────────────────
-- These must be run AFTER SQLAlchemy creates the base tables via init_db().
-- We use a separate migration step for this.
-- See: scripts/setup.sh which calls `make migrate` first.

-- The DO block below is idempotent — safe to run multiple times.
DO $$
BEGIN
    -- water_quality_readings hypertable (partitioned by measured_at)
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'water_quality_readings'
    ) AND NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_name = 'water_quality_readings'
    ) THEN
        PERFORM create_hypertable(
            'water_quality_readings',
            'measured_at',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        );
        RAISE NOTICE 'Created hypertable: water_quality_readings';
    END IF;

    -- fish_growth_records hypertable
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'fish_growth_records'
    ) AND NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_name = 'fish_growth_records'
    ) THEN
        PERFORM create_hypertable(
            'fish_growth_records',
            'measured_at',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
        RAISE NOTICE 'Created hypertable: fish_growth_records';
    END IF;

    -- feeding_records hypertable
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'feeding_records'
    ) AND NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_name = 'feeding_records'
    ) THEN
        PERFORM create_hypertable(
            'feeding_records',
            'started_at',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
        RAISE NOTICE 'Created hypertable: feeding_records';
    END IF;
END
$$;

-- Continuous aggregates for 1-hour water quality rollups
-- TODO (Phase 2): Create after hypertables are confirmed working
-- CREATE MATERIALIZED VIEW water_quality_hourly
-- WITH (timescaledb.continuous) AS
-- SELECT
--     time_bucket('1 hour', measured_at) AS bucket,
--     tank_id,
--     AVG(temperature_c) AS avg_temp,
--     AVG(ph) AS avg_ph,
--     AVG(dissolved_oxygen_mgl) AS avg_do,
--     AVG(ammonia_ppm) AS avg_ammonia
-- FROM water_quality_readings
-- GROUP BY bucket, tank_id;
