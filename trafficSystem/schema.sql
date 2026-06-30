-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- CCTV cameras table
CREATE TABLE cameras (
    id          VARCHAR(50) PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    location    GEOGRAPHY(POINT, 4326) NOT NULL,
    stream_url  TEXT,
    is_active   BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Hazard / restricted zones (polygon)
CREATE TABLE zones (
    id          VARCHAR(50) PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    type        VARCHAR(50) NOT NULL,
    color       VARCHAR(7)  NOT NULL,
    boundary    GEOGRAPHY(POLYGON, 4326) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Violations log table (written by CV worker or simulator via backend)
CREATE TABLE violations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id   VARCHAR(50) REFERENCES cameras(id),
    type        VARCHAR(50) NOT NULL,
    location    GEOGRAPHY(POINT, 4326) NOT NULL,
    severity    VARCHAR(20) NOT NULL,
    snapshot_url TEXT,
    occurred_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX violations_occurred_at_idx ON violations (occurred_at DESC);

-- Jakarta Events table
CREATE TABLE events (
    id                  VARCHAR(50) PRIMARY KEY,
    name                VARCHAR(300) NOT NULL,
    venue               VARCHAR(200) NOT NULL,
    location            GEOGRAPHY(POINT, 4326) NOT NULL,
    event_date          DATE NOT NULL,
    event_time          TIME NOT NULL,
    estimated_crowd     INTEGER NOT NULL,
    impact_radius_km    FLOAT NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
