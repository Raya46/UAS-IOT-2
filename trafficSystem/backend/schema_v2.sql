-- =============================================================
-- EXTENSION (sudah ada dari V1, pastikan aktif)
-- =============================================================
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================
-- TAMBAHAN KOLOM KE TABEL violations (V1)
-- =============================================================
ALTER TABLE violations
  ADD COLUMN IF NOT EXISTS confidence_score   FLOAT DEFAULT 0.5,
  ADD COLUMN IF NOT EXISTS source_count       INTEGER DEFAULT 1,
  ADD COLUMN IF NOT EXISTS status             VARCHAR(20) DEFAULT 'detected',
  ADD COLUMN IF NOT EXISTS assigned_officer   VARCHAR(100),
  ADD COLUMN IF NOT EXISTS resolved_at        TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS resolution_notes   TEXT,
  ADD COLUMN IF NOT EXISTS parent_incident_id UUID REFERENCES violations(id),
  ADD COLUMN IF NOT EXISTS duplicate_of       UUID REFERENCES violations(id);

-- Index untuk lifecycle queries
CREATE INDEX IF NOT EXISTS violations_status_idx ON violations (status);
CREATE INDEX IF NOT EXISTS violations_location_idx ON violations USING GIST (location);

-- =============================================================
-- TABEL BARU: incidents (agregasi dari violations)
-- =============================================================
CREATE TABLE IF NOT EXISTS incidents (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  title             VARCHAR(300) NOT NULL,
  type              VARCHAR(50) NOT NULL,
  location          GEOGRAPHY(POINT, 4326) NOT NULL,
  severity          VARCHAR(20) NOT NULL DEFAULT 'medium',
  confidence_score  FLOAT NOT NULL DEFAULT 0.5,
  status            VARCHAR(20) NOT NULL DEFAULT 'detected',
  -- Status lifecycle: detected → confirmed → dispatched → resolved → closed
  source_violations UUID[] DEFAULT '{}',
  source_count      INTEGER DEFAULT 1,
  assigned_officer  VARCHAR(100),
  assigned_at       TIMESTAMPTZ,
  resolved_at       TIMESTAMPTZ,
  resolution_notes  TEXT,
  snapshot_url      TEXT,
  description       TEXT,
  vehicle_type      VARCHAR(80),
  plate_number      VARCHAR(40),
  plate_crop        TEXT,
  plate_bbox        JSONB,
  plate_confidence  FLOAT,
  plate_note        TEXT,
  video_time_seconds FLOAT,
  camera_id         VARCHAR(50) REFERENCES cameras(id),
  occurred_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE incidents
  ADD COLUMN IF NOT EXISTS description TEXT,
  ADD COLUMN IF NOT EXISTS vehicle_type VARCHAR(80),
  ADD COLUMN IF NOT EXISTS plate_number VARCHAR(40),
  ADD COLUMN IF NOT EXISTS plate_crop TEXT,
  ADD COLUMN IF NOT EXISTS plate_bbox JSONB,
  ADD COLUMN IF NOT EXISTS plate_confidence FLOAT,
  ADD COLUMN IF NOT EXISTS plate_note TEXT,
  ADD COLUMN IF NOT EXISTS video_time_seconds FLOAT;

CREATE INDEX IF NOT EXISTS incidents_status_idx ON incidents (status);
CREATE INDEX IF NOT EXISTS incidents_occurred_at_idx ON incidents (occurred_at DESC);
CREATE INDEX IF NOT EXISTS incidents_location_idx ON incidents USING GIST (location);
CREATE INDEX IF NOT EXISTS incidents_type_idx ON incidents (type);

-- =============================================================
-- TABEL BARU: risk_zones (hasil kalkulasi risk profiling)
-- =============================================================
CREATE TABLE IF NOT EXISTS risk_zones (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name            VARCHAR(200),
  location        GEOGRAPHY(POINT, 4326) NOT NULL,
  risk_score      FLOAT NOT NULL DEFAULT 0.0,  -- 0.0 sampai 1.0
  violation_types TEXT[] DEFAULT '{}',          -- tipe pelanggaran dominan
  incident_count  INTEGER DEFAULT 0,
  peak_hours      INTEGER[] DEFAULT '{}',        -- jam-jam rawan (0-23)
  peak_days       INTEGER[] DEFAULT '{}',        -- hari rawan (0=Senin, 6=Minggu)
  radius_m        FLOAT DEFAULT 100.0,
  calculated_at   TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT risk_score_range CHECK (risk_score >= 0.0 AND risk_score <= 1.0)
);

CREATE INDEX IF NOT EXISTS risk_zones_score_idx ON risk_zones (risk_score DESC);
CREATE INDEX IF NOT EXISTS risk_zones_location_idx ON risk_zones USING GIST (location);

-- =============================================================
-- TABEL BARU: placement_recommendations
-- =============================================================
CREATE TABLE IF NOT EXISTS placement_recommendations (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  location            GEOGRAPHY(POINT, 4326) NOT NULL,
  recommendation_type VARCHAR(20) NOT NULL,  -- 'camera_etle' | 'officer'
  priority_rank       INTEGER NOT NULL,
  risk_score          FLOAT NOT NULL,
  violation_types     TEXT[] DEFAULT '{}',
  coverage_radius_m   FLOAT DEFAULT 150.0,
  rationale           TEXT,
  generated_at        TIMESTAMPTZ DEFAULT NOW(),
  is_active           BOOLEAN DEFAULT true
);

-- =============================================================
-- TABEL BARU: daily_reports
-- =============================================================
CREATE TABLE IF NOT EXISTS daily_reports (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  report_date         DATE NOT NULL UNIQUE,
  total_incidents     INTEGER DEFAULT 0,
  by_type             JSONB DEFAULT '{}',    -- {"busway_violation": 12, "illegal_parking": 34}
  by_severity         JSONB DEFAULT '{}',    -- {"high": 5, "medium": 20, "low": 21}
  by_hour             JSONB DEFAULT '{}',    -- {"0": 2, "1": 1, ..., "23": 8}
  top_locations       JSONB DEFAULT '[]',    -- [{lat, lng, count, type}]
  avg_response_time_s INTEGER,
  resolved_count      INTEGER DEFAULT 0,
  pdf_url             TEXT,
  generated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- TABEL BARU: event_predictions (output dari congestion predictor)
-- =============================================================
CREATE TABLE IF NOT EXISTS event_predictions (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  event_id            VARCHAR(50) NOT NULL,
  event_name          VARCHAR(300) NOT NULL,
  predicted_at        TIMESTAMPTZ DEFAULT NOW(),
  impact_start        TIMESTAMPTZ NOT NULL,
  impact_end          TIMESTAMPTZ NOT NULL,
  affected_segments   JSONB DEFAULT '[]',  -- [{segment_id, congestion_level, coordinates}]
  mitigation_actions  JSONB DEFAULT '[]',  -- [{action, location, priority}]
  confidence          FLOAT DEFAULT 0.7
);

-- =============================================================
-- TABEL BARU: external_events (dari scraper portal Jakarta)
-- =============================================================
CREATE TABLE IF NOT EXISTS external_events (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  external_id       VARCHAR(200) UNIQUE,
  source            VARCHAR(50),            -- 'tiket_com' | 'loket_com' | 'manual' | 'jakartago'
  name              VARCHAR(500) NOT NULL,
  venue             VARCHAR(300),
  location          GEOGRAPHY(POINT, 4326),
  event_date        DATE NOT NULL,
  event_time        TIME,
  end_time          TIME,
  estimated_crowd   INTEGER DEFAULT 0,
  category          VARCHAR(100),           -- 'concert' | 'sports' | 'marathon' | 'fair'
  raw_data          JSONB DEFAULT '{}',
  scraped_at        TIMESTAMPTZ DEFAULT NOW(),
  is_verified       BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS external_events_date_idx ON external_events (event_date);
CREATE INDEX IF NOT EXISTS external_events_location_idx ON external_events USING GIST (location);

-- =============================================================
-- VIEW: violation_heatmap_data (untuk modul C)
-- =============================================================
CREATE OR REPLACE VIEW violation_heatmap_data AS
SELECT
  ST_X(location::geometry)                    AS lng,
  ST_Y(location::geometry)                    AS lat,
  type,
  severity,
  confidence_score,
  EXTRACT(HOUR FROM occurred_at)::INTEGER      AS hour_of_day,
  EXTRACT(DOW FROM occurred_at)::INTEGER       AS day_of_week,
  DATE(occurred_at)                            AS incident_date,
  occurred_at
FROM incidents
WHERE occurred_at >= NOW() - INTERVAL '90 days';

-- =============================================================
-- FUNCTION: calculate_risk_zones (dijalankan via cron harian)
-- =============================================================
CREATE OR REPLACE FUNCTION calculate_risk_zones()
RETURNS void AS $$
BEGIN
  DELETE FROM risk_zones;

  INSERT INTO risk_zones (location, risk_score, violation_types, incident_count, peak_hours, peak_days, radius_m)
  SELECT
    ST_Centroid(ST_Collect(location::geometry))::geography AS location,
    LEAST(COUNT(*)::float / 50.0, 1.0)                     AS risk_score,
    ARRAY_AGG(DISTINCT type)                                AS violation_types,
    COUNT(*)                                                AS incident_count,
    ARRAY_AGG(DISTINCT EXTRACT(HOUR FROM occurred_at)::INTEGER) AS peak_hours,
    ARRAY_AGG(DISTINCT EXTRACT(DOW FROM occurred_at)::INTEGER)  AS peak_days,
    100.0                                                   AS radius_m
  FROM incidents
  WHERE occurred_at >= NOW() - INTERVAL '30 days'
  GROUP BY ST_SnapToGrid(location::geometry, 0.001)
  HAVING COUNT(*) >= 1;
END;
$$ LANGUAGE plpgsql;
-- =============================================================
-- DATA SEEDING (untuk CCTV, Zones dan Events awal)
-- =============================================================
DELETE FROM violations WHERE camera_id IN ('cam-005', 'cam-006');
DELETE FROM incidents WHERE camera_id IN ('cam-005', 'cam-006');
DELETE FROM cameras WHERE id IN ('cam-005', 'cam-006');

INSERT INTO cameras (id, name, location, stream_url) VALUES
  ('cam-001', 'Gelora', ST_SetSRID(ST_MakePoint(106.801000, -6.216600), 4326)::geography, 'https://cctv.balitower.co.id/Gelora-017-700470_2/embed.html'),
  ('cam-002', 'Bendungan Hilir', ST_SetSRID(ST_MakePoint(106.811500, -6.213300), 4326)::geography, 'https://cctv.balitower.co.id/Bendungan-Hilir-003-700014_1/embed.html'),
  ('cam-003', 'Jati Pulo', ST_SetSRID(ST_MakePoint(106.802800, -6.184300), 4326)::geography, 'https://cctv.balitower.co.id/Jati-Pulo-001-702017_2/embed.html'),
  ('cam-004', 'Cikoko', ST_SetSRID(ST_MakePoint(106.855400, -6.242800), 4326)::geography, 'https://cctv.balitower.co.id/Cikoko-006-705651_2/embed.html')
ON CONFLICT (id) DO UPDATE SET 
  name = EXCLUDED.name,
  location = EXCLUDED.location,
  stream_url = EXCLUDED.stream_url;

INSERT INTO zones (id, name, type, color, boundary) VALUES
  ('zone-busway-1', 'Koridor Transjakarta — Sudirman', 'busway_corridor', '#FF6B00', ST_SetSRID(ST_GeomFromText('POLYGON((106.8200 -6.1800, 106.8210 -6.1800, 106.8210 -6.2100, 106.8200 -6.2100, 106.8200 -6.1800))'), 4326)::geography),
  ('zone-parking-1', 'Zona Rawan Parkir Liar — Tanah Abang', 'illegal_parking', '#FFD700', ST_SetSRID(ST_GeomFromText('POLYGON((106.8130 -6.1870, 106.8160 -6.1870, 106.8160 -6.1900, 106.8130 -6.1900, 106.8130 -6.1870))'), 4326)::geography)
ON CONFLICT (id) DO NOTHING;

INSERT INTO events (id, name, venue, location, event_date, event_time, estimated_crowd, impact_radius_km) VALUES
  ('evt-001', 'Konser Coldplay Jakarta', 'GBK', ST_SetSRID(ST_MakePoint(106.8018, -6.2183), 4326)::geography, '2026-07-15', '19:00:00', 80000, 2.5),
  ('evt-002', 'Final Piala Indonesia', 'JIS', ST_SetSRID(ST_MakePoint(106.8676, -6.1275), 4326)::geography, '2026-07-20', '20:00:00', 50000, 2.0)
ON CONFLICT (id) DO NOTHING;
