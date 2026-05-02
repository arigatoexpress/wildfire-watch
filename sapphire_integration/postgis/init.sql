-- wildfire-watch PostGIS schema (v1.0.0)
--
-- Mirror of the Foundry ontology in sapphire_integration/foundry/ontology.py.
-- This is the system-of-record per docs/intel/foundry-research-2026-05-01.md
-- (recommended path: Postgres+PostGIS for primary state, Foundry as the
-- ontology + AIP demo layer).
--
-- Tested against PostgreSQL 16 + PostGIS 3.4. Run as the wildfire_watch
-- database superuser. The companion docker-compose.yml provisions a local
-- instance.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Reference: SRID 4326 (WGS84) for all geometry. Z values in meters MSL.
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS wfw;

-- ---------------------------------------------------------------------------
-- Drone
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wfw.drone (
    drone_id              TEXT PRIMARY KEY
        CHECK (drone_id ~ '^wfw-[a-z0-9]{4,16}$'),
    airframe_class        TEXT NOT NULL
        CHECK (airframe_class IN (
            'mavic_mini_2', 'holybro_x500_v2',
            'skydio_x10', 'teal_2', 'parrot_anafi_usa_gov',
            'generic_quad', 'sim_only'
        )),
    rpic_pilot_license_id TEXT,
    insurance_policy_ref  TEXT,
    maintenance_log_uri   TEXT,
    blue_uas_status       TEXT NOT NULL DEFAULT 'unknown'
        CHECK (blue_uas_status IN ('cleared', 'substitutable', 'non_eligible', 'unknown')),
    registered_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata              JSONB DEFAULT '{}'::jsonb
);

-- ---------------------------------------------------------------------------
-- Zone (a monitored polygon — inclusion or exclusion)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wfw.zone (
    zone_id               TEXT PRIMARY KEY,
    corridor              TEXT NOT NULL,
    polygon               GEOGRAPHY(POLYGON, 4326) NOT NULL,
    fuel_load_class       TEXT NOT NULL DEFAULT 'moderate'
        CHECK (fuel_load_class IN ('low', 'moderate', 'moderate-high', 'high', 'extreme')),
    primary_risk          TEXT NOT NULL DEFAULT 'unknown',
    elevation_min_m       REAL NOT NULL DEFAULT 0,
    elevation_max_m       REAL NOT NULL DEFAULT 0,
    last_patrol_at        TIMESTAMPTZ,
    is_exclusion          BOOLEAN NOT NULL DEFAULT FALSE,
    regulatory_basis      TEXT,
    metadata              JSONB DEFAULT '{}'::jsonb,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS zone_polygon_gix ON wfw.zone USING GIST (polygon);
CREATE INDEX IF NOT EXISTS zone_corridor_idx ON wfw.zone (corridor);
CREATE INDEX IF NOT EXISTS zone_exclusion_idx ON wfw.zone (is_exclusion) WHERE is_exclusion = TRUE;

-- ---------------------------------------------------------------------------
-- Fire Department Unit
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wfw.fire_department_unit (
    unit_id               TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    aor                   GEOGRAPHY(POLYGON, 4326),
    primary_contact_name  TEXT,
    primary_contact_role  TEXT,
    dispatch_phone        TEXT,
    physical_address      TEXT,
    engagement_status     TEXT NOT NULL DEFAULT 'not_contacted'
        CHECK (engagement_status IN (
            'not_contacted', 'outreached', 'engaged',
            'loa_signed', 'operational_partner'
        )),
    last_contact_at       TIMESTAMPTZ,
    metadata              JSONB DEFAULT '{}'::jsonb,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS fdu_aor_gix ON wfw.fire_department_unit USING GIST (aor);
CREATE INDEX IF NOT EXISTS fdu_engagement_idx ON wfw.fire_department_unit (engagement_status);

-- ---------------------------------------------------------------------------
-- Flight Log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wfw.flight_log (
    flight_id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drone_id                  TEXT NOT NULL REFERENCES wfw.drone(drone_id),
    mission_yaml_uri          TEXT,
    started_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at                  TIMESTAMPTZ,
    is_sim                    BOOLEAN NOT NULL DEFAULT TRUE,
    recording_dir_uri         TEXT,
    total_distance_km         REAL DEFAULT 0,
    total_duration_s          REAL DEFAULT 0,
    signals_emitted           INTEGER DEFAULT 0,
    consensus_signals_emitted INTEGER DEFAULT 0,
    geofence_breaches         INTEGER DEFAULT 0,
    battery_consumed_pct      REAL DEFAULT 0,
    metadata                  JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS flight_log_drone_idx ON wfw.flight_log (drone_id);
CREATE INDEX IF NOT EXISTS flight_log_started_idx ON wfw.flight_log (started_at);
CREATE INDEX IF NOT EXISTS flight_log_is_sim_idx ON wfw.flight_log (is_sim);

-- ---------------------------------------------------------------------------
-- Battery Cycle
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wfw.battery_cycle (
    cycle_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    battery_serial    TEXT NOT NULL,
    chemistry         TEXT NOT NULL DEFAULT 'unknown'
        CHECK (chemistry IN ('lipo', 'li_ion', 'lifepo4', 'unknown')),
    capacity_mah      INTEGER NOT NULL DEFAULT 0,
    flight_id         UUID REFERENCES wfw.flight_log(flight_id) ON DELETE SET NULL,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at          TIMESTAMPTZ,
    starting_voltage_v REAL DEFAULT 0,
    ending_voltage_v  REAL DEFAULT 0,
    coldest_temp_c    REAL,
    notes             TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS battery_serial_idx ON wfw.battery_cycle (battery_serial);
CREATE INDEX IF NOT EXISTS battery_flight_idx ON wfw.battery_cycle (flight_id);

-- ---------------------------------------------------------------------------
-- Wildfire Signal — the v1 schema as a relational table.
-- The full v1 JSON payload lives in raw_payload (JSONB) for forward-compat;
-- the indexed columns are the operational hot path.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wfw.wildfire_signal (
    signal_id           UUID PRIMARY KEY,
    drone_id            TEXT NOT NULL REFERENCES wfw.drone(drone_id),
    zone_id             TEXT NOT NULL REFERENCES wfw.zone(zone_id),
    flight_id           UUID REFERENCES wfw.flight_log(flight_id) ON DELETE SET NULL,
    timestamp           TIMESTAMPTZ NOT NULL,
    location            GEOGRAPHY(POINTZ, 4326) NOT NULL,
    target_location     GEOGRAPHY(POINTZ, 4326),
    signal_type         TEXT NOT NULL
        CHECK (signal_type IN (
            'smoke', 'fire', 'thermal_anomaly',
            'wildlife', 'anomaly', 'system_event'
        )),
    signal_subtype      TEXT,
    confidence          REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    risk_score          REAL NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    recommended_action  TEXT NOT NULL
        CHECK (recommended_action IN (
            'log_only', 'notify_operator', 'notify_fire_dept',
            'loiter_and_capture', 'rtl'
        )),
    consensus_peers     TEXT[],
    schema_version      TEXT NOT NULL DEFAULT '1.0.0',
    raw_payload         JSONB NOT NULL,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS wfs_location_gix ON wfw.wildfire_signal USING GIST (location);
CREATE INDEX IF NOT EXISTS wfs_target_gix ON wfw.wildfire_signal USING GIST (target_location);
CREATE INDEX IF NOT EXISTS wfs_zone_idx ON wfw.wildfire_signal (zone_id);
CREATE INDEX IF NOT EXISTS wfs_drone_idx ON wfw.wildfire_signal (drone_id);
CREATE INDEX IF NOT EXISTS wfs_timestamp_idx ON wfw.wildfire_signal (timestamp DESC);
CREATE INDEX IF NOT EXISTS wfs_signal_type_idx ON wfw.wildfire_signal (signal_type);
CREATE INDEX IF NOT EXISTS wfs_recommended_action_idx ON wfw.wildfire_signal (recommended_action);
CREATE INDEX IF NOT EXISTS wfs_risk_high_idx ON wfw.wildfire_signal (risk_score DESC) WHERE risk_score >= 60;

-- ---------------------------------------------------------------------------
-- Operational views
-- ---------------------------------------------------------------------------

-- 24h summary by zone — replaces the wildfire plugin tool's stats action when
-- a real DB is available.
CREATE OR REPLACE VIEW wfw.signals_24h_by_zone AS
SELECT
    zone_id,
    COUNT(*) AS signals_count,
    COUNT(*) FILTER (WHERE signal_type = 'fire') AS fire_count,
    COUNT(*) FILTER (WHERE signal_type = 'smoke') AS smoke_count,
    COUNT(*) FILTER (WHERE signal_type = 'thermal_anomaly') AS thermal_count,
    COUNT(*) FILTER (WHERE recommended_action = 'notify_fire_dept') AS critical_count,
    MAX(risk_score) AS max_risk_score,
    AVG(risk_score) AS avg_risk_score,
    MAX(timestamp) AS most_recent_at
FROM wfw.wildfire_signal
WHERE timestamp >= NOW() - INTERVAL '24 hours'
GROUP BY zone_id;

-- Spatial query: signals within a radius of a point (e.g. nearest 5 km of CBFPD HQ).
-- Called as: SELECT * FROM wfw.signals_within('38.8697', '-106.9878', 5000);
CREATE OR REPLACE FUNCTION wfw.signals_within(
    center_lat   DOUBLE PRECISION,
    center_lon   DOUBLE PRECISION,
    radius_m     DOUBLE PRECISION
) RETURNS SETOF wfw.wildfire_signal AS $$
    SELECT *
    FROM wfw.wildfire_signal
    WHERE ST_DWithin(
        location,
        ST_SetSRID(ST_MakePoint(center_lon, center_lat), 4326)::geography,
        radius_m
    )
    ORDER BY timestamp DESC
$$ LANGUAGE SQL STABLE;

-- Geofence breach detection: any signal that fell INSIDE a registered exclusion zone.
CREATE OR REPLACE VIEW wfw.geofence_breaches AS
SELECT
    s.signal_id,
    s.timestamp,
    s.drone_id,
    s.zone_id  AS reported_zone_id,
    z.zone_id  AS breached_exclusion_zone_id,
    z.regulatory_basis
FROM wfw.wildfire_signal s
JOIN wfw.zone z
  ON z.is_exclusion = TRUE
 AND ST_Within(s.location::geometry, z.polygon::geometry);

-- ---------------------------------------------------------------------------
-- Audit + idempotency: the v1 signal_id is a UUIDv4 generated drone-side at
-- emit time. Re-ingesting the same id is a no-op (matches the Sapphire
-- bridge's idempotency contract).
-- ---------------------------------------------------------------------------
COMMENT ON TABLE wfw.wildfire_signal IS
    'Idempotent on signal_id (drone-side UUIDv4). Re-INSERT with conflicting id should be ON CONFLICT DO NOTHING.';
