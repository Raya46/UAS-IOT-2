BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
  ('cam-001', 'Bundaran HI', ST_SetSRID(ST_MakePoint(106.8229, -6.1944), 4326)::geography, '/videos/cam001.mp4', true),
  ('cam-002', 'Semanggi', ST_SetSRID(ST_MakePoint(106.8228, -6.2088), 4326)::geography, '/videos/cam002.mp4', true),
  ('cam-003', 'Blok M', ST_SetSRID(ST_MakePoint(106.7993, -6.2441), 4326)::geography, '/videos/cam003.mp4', true),
  ('cam-004', 'Sarinah', ST_SetSRID(ST_MakePoint(106.8226, -6.1867), 4326)::geography, '/videos/cam004.mp4', true),
  ('cam-005', 'GBK Pintu 10', ST_SetSRID(ST_MakePoint(106.8023, -6.2197), 4326)::geography, '/videos/cam005.mp4', true),
  ('cam-006', 'Tanah Abang', ST_SetSRID(ST_MakePoint(106.8156, -6.1889), 4326)::geography, '/videos/cam006.mp4', true),
  ('cam-007', 'Kuningan Barat', ST_SetSRID(ST_MakePoint(106.8309, -6.2365), 4326)::geography, '/videos/cam007.mp4', true),
  ('cam-008', 'Manggarai', ST_SetSRID(ST_MakePoint(106.8502, -6.2088), 4326)::geography, '/videos/cam008.mp4', true)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  location = EXCLUDED.location,
  stream_url = EXCLUDED.stream_url,
  is_active = EXCLUDED.is_active;

INSERT INTO zones (id, name, type, color, boundary) VALUES
  ('zone-busway-1', 'Koridor Transjakarta - Sudirman', 'busway_corridor', '#FF6B00', ST_SetSRID(ST_GeomFromText('POLYGON((106.8200 -6.1800, 106.8210 -6.1800, 106.8210 -6.2100, 106.8200 -6.2100, 106.8200 -6.1800))'), 4326)::geography),
  ('zone-parking-1', 'Zona Rawan Parkir Liar - Tanah Abang', 'illegal_parking', '#FFD700', ST_SetSRID(ST_GeomFromText('POLYGON((106.8130 -6.1870, 106.8160 -6.1870, 106.8160 -6.1900, 106.8130 -6.1900, 106.8130 -6.1870))'), 4326)::geography),
  ('zone-event-gbk', 'Area Dampak Event GBK', 'event_impact', '#9B59B6', ST_SetSRID(ST_GeomFromText('POLYGON((106.7920 -6.2110, 106.8120 -6.2110, 106.8120 -6.2280, 106.7920 -6.2280, 106.7920 -6.2110))'), 4326)::geography),
  ('zone-congestion-1', 'Koridor Macet Manggarai', 'congestion', '#E74C3C', ST_SetSRID(ST_GeomFromText('POLYGON((106.8450 -6.2040, 106.8540 -6.2040, 106.8540 -6.2130, 106.8450 -6.2130, 106.8450 -6.2040))'), 4326)::geography)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  type = EXCLUDED.type,
  color = EXCLUDED.color,
  boundary = EXCLUDED.boundary;

INSERT INTO events (id, name, venue, location, event_date, event_time, estimated_crowd, impact_radius_km) VALUES
  ('evt-001', 'Konser Coldplay Jakarta', 'GBK', ST_SetSRID(ST_MakePoint(106.8018, -6.2183), 4326)::geography, CURRENT_DATE + 7, '19:00:00', 80000, 2.5),
  ('evt-002', 'Final Piala Indonesia', 'JIS', ST_SetSRID(ST_MakePoint(106.8676, -6.1275), 4326)::geography, CURRENT_DATE + 12, '20:00:00', 50000, 2.0),
  ('evt-003', 'Jakarta Night Run', 'Monas', ST_SetSRID(ST_MakePoint(106.8272, -6.1754), 4326)::geography, CURRENT_DATE + 3, '21:00:00', 22000, 1.7)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  venue = EXCLUDED.venue,
  location = EXCLUDED.location,
  event_date = EXCLUDED.event_date,
  event_time = EXCLUDED.event_time,
  estimated_crowd = EXCLUDED.estimated_crowd,
  impact_radius_km = EXCLUDED.impact_radius_km;

INSERT INTO incidents (
  id, title, type, location, severity, confidence_score, status,
  source_count, assigned_officer, assigned_at, resolved_at, resolution_notes,
  snapshot_url, camera_id, occurred_at, updated_at
) VALUES
  ('10000000-0000-0000-0000-000000000001', 'Parkir liar menutup satu lajur di Tanah Abang', 'illegal_parking', ST_SetSRID(ST_MakePoint(106.8156, -6.1889), 4326)::geography, 'high', 0.94, 'confirmed', 5, 'Unit Patroli A1', NOW() - INTERVAL '35 minutes', NULL, NULL, '/evidence/tanah-abang-parking-01.jpg', 'cam-006', NOW() - INTERVAL '55 minutes', NOW() - INTERVAL '10 minutes'),
  ('10000000-0000-0000-0000-000000000002', 'Kendaraan masuk jalur busway Sudirman', 'busway_violation', ST_SetSRID(ST_MakePoint(106.8211, -6.1976), 4326)::geography, 'medium', 0.86, 'detected', 3, NULL, NULL, NULL, NULL, '/evidence/sudirman-busway-01.jpg', 'cam-001', NOW() - INTERVAL '75 minutes', NOW() - INTERVAL '75 minutes'),
  ('10000000-0000-0000-0000-000000000003', 'Kemacetan meningkat di simpang Semanggi', 'congestion', ST_SetSRID(ST_MakePoint(106.8228, -6.2088), 4326)::geography, 'high', 0.91, 'dispatched', 7, 'Unit Urai C3', NOW() - INTERVAL '50 minutes', NULL, NULL, '/evidence/semanggi-congestion-01.jpg', 'cam-002', NOW() - INTERVAL '1 hour 40 minutes', NOW() - INTERVAL '15 minutes'),
  ('10000000-0000-0000-0000-000000000004', 'Kendaraan melawan arah di Blok M', 'wrong_way', ST_SetSRID(ST_MakePoint(106.7993, -6.2441), 4326)::geography, 'high', 0.89, 'resolved', 4, 'Unit Patroli B2', NOW() - INTERVAL '3 hours 20 minutes', NOW() - INTERVAL '2 hours 35 minutes', 'Pengendara diberhentikan dan arus kembali normal.', '/evidence/blokm-wrongway-01.jpg', 'cam-003', NOW() - INTERVAL '4 hours', NOW() - INTERVAL '2 hours 35 minutes'),
  ('10000000-0000-0000-0000-000000000005', 'Antrean kendaraan sekitar pintu GBK', 'congestion', ST_SetSRID(ST_MakePoint(106.8023, -6.2197), 4326)::geography, 'medium', 0.82, 'confirmed', 6, 'Unit Event GBK', NOW() - INTERVAL '1 hour 20 minutes', NULL, NULL, '/evidence/gbk-congestion-01.jpg', 'cam-005', NOW() - INTERVAL '2 hours 10 minutes', NOW() - INTERVAL '25 minutes'),
  ('10000000-0000-0000-0000-000000000006', 'Parkir liar depan pusat belanja Sarinah', 'illegal_parking', ST_SetSRID(ST_MakePoint(106.8226, -6.1867), 4326)::geography, 'medium', 0.77, 'closed', 2, 'Unit Patroli A2', NOW() - INTERVAL '1 day 2 hours', NOW() - INTERVAL '1 day 1 hour 20 minutes', 'Kendaraan dipindahkan oleh petugas.', '/evidence/sarinah-parking-01.jpg', 'cam-004', NOW() - INTERVAL '1 day 3 hours', NOW() - INTERVAL '1 day 1 hour 20 minutes'),
  ('10000000-0000-0000-0000-000000000007', 'Lampu hazard digunakan saat bergerak di Kuningan', 'hazard_lights', ST_SetSRID(ST_MakePoint(106.8309, -6.2365), 4326)::geography, 'low', 0.69, 'resolved', 1, 'Unit Edukasi Lalin', NOW() - INTERVAL '1 day 5 hours', NOW() - INTERVAL '1 day 4 hours 45 minutes', 'Peringatan diberikan.', '/evidence/kuningan-hazard-01.jpg', 'cam-007', NOW() - INTERVAL '1 day 5 hours 30 minutes', NOW() - INTERVAL '1 day 4 hours 45 minutes'),
  ('10000000-0000-0000-0000-000000000008', 'Kemacetan sekitar Stasiun Manggarai', 'congestion', ST_SetSRID(ST_MakePoint(106.8502, -6.2088), 4326)::geography, 'high', 0.93, 'dispatched', 8, 'Unit Urai M1', NOW() - INTERVAL '2 hours 15 minutes', NULL, NULL, '/evidence/manggarai-congestion-01.jpg', 'cam-008', NOW() - INTERVAL '2 hours 45 minutes', NOW() - INTERVAL '35 minutes'),
  ('10000000-0000-0000-0000-000000000009', 'Parkir liar berulang di Tanah Abang', 'illegal_parking', ST_SetSRID(ST_MakePoint(106.8152, -6.1892), 4326)::geography, 'high', 0.88, 'resolved', 4, 'Unit Patroli A1', NOW() - INTERVAL '2 days 3 hours', NOW() - INTERVAL '2 days 2 hours 10 minutes', 'Area disterilkan.', '/evidence/tanah-abang-parking-02.jpg', 'cam-006', NOW() - INTERVAL '2 days 4 hours', NOW() - INTERVAL '2 days 2 hours 10 minutes'),
  ('10000000-0000-0000-0000-000000000010', 'Pelanggaran busway dekat Bundaran HI', 'busway_violation', ST_SetSRID(ST_MakePoint(106.8214, -6.1938), 4326)::geography, 'medium', 0.81, 'resolved', 2, 'Unit ETLE 01', NOW() - INTERVAL '3 days 1 hour', NOW() - INTERVAL '3 days 25 minutes', 'Tilang elektronik diterbitkan.', '/evidence/hi-busway-02.jpg', 'cam-001', NOW() - INTERVAL '3 days 2 hours', NOW() - INTERVAL '3 days 25 minutes'),
  ('10000000-0000-0000-0000-000000000011', 'Kepadatan kendaraan pasca jam kantor di Semanggi', 'congestion', ST_SetSRID(ST_MakePoint(106.8230, -6.2093), 4326)::geography, 'medium', 0.84, 'resolved', 5, 'Unit Urai C3', NOW() - INTERVAL '4 days 1 hour', NOW() - INTERVAL '4 days 20 minutes', 'Contraflow lokal selesai.', '/evidence/semanggi-congestion-02.jpg', 'cam-002', NOW() - INTERVAL '4 days 2 hours', NOW() - INTERVAL '4 days 20 minutes'),
  ('10000000-0000-0000-0000-000000000012', 'Kendaraan berhenti di bahu jalan Sudirman', 'illegal_parking', ST_SetSRID(ST_MakePoint(106.8208, -6.2012), 4326)::geography, 'low', 0.71, 'closed', 1, 'Unit Patroli A3', NOW() - INTERVAL '5 days 5 hours', NOW() - INTERVAL '5 days 4 hours 30 minutes', 'Pemilik kendaraan diarahkan pindah.', '/evidence/sudirman-parking-01.jpg', 'cam-001', NOW() - INTERVAL '5 days 6 hours', NOW() - INTERVAL '5 days 4 hours 30 minutes')
ON CONFLICT (id) DO UPDATE SET
  title = EXCLUDED.title,
  type = EXCLUDED.type,
  location = EXCLUDED.location,
  severity = EXCLUDED.severity,
  confidence_score = EXCLUDED.confidence_score,
  status = EXCLUDED.status,
  source_count = EXCLUDED.source_count,
  assigned_officer = EXCLUDED.assigned_officer,
  assigned_at = EXCLUDED.assigned_at,
  resolved_at = EXCLUDED.resolved_at,
  resolution_notes = EXCLUDED.resolution_notes,
  snapshot_url = EXCLUDED.snapshot_url,
  camera_id = EXCLUDED.camera_id,
  occurred_at = EXCLUDED.occurred_at,
  updated_at = EXCLUDED.updated_at;

WITH demo_incidents AS (
  SELECT
    ROW_NUMBER() OVER (ORDER BY occurred_at DESC) AS n,
    id,
    camera_id,
    type,
    location,
    severity,
    snapshot_url,
    occurred_at,
    confidence_score,
    source_count,
    status,
    assigned_officer,
    resolved_at,
    resolution_notes
  FROM incidents
  WHERE id::text LIKE '10000000-0000-0000-0000-0000000000%'
)
INSERT INTO violations (
  id, camera_id, type, location, severity, snapshot_url, occurred_at,
  confidence_score, source_count, status, assigned_officer, resolved_at,
  resolution_notes
)
SELECT
  ('20000000-0000-0000-0000-0000000000' || LPAD(n::text, 2, '0'))::uuid,
  camera_id,
  type,
  location,
  severity,
  snapshot_url,
  occurred_at,
  confidence_score,
  source_count,
  status,
  assigned_officer,
  resolved_at,
  resolution_notes
FROM demo_incidents
ON CONFLICT (id) DO UPDATE SET
  camera_id = EXCLUDED.camera_id,
  type = EXCLUDED.type,
  location = EXCLUDED.location,
  severity = EXCLUDED.severity,
  snapshot_url = EXCLUDED.snapshot_url,
  occurred_at = EXCLUDED.occurred_at,
  confidence_score = EXCLUDED.confidence_score,
  source_count = EXCLUDED.source_count,
  status = EXCLUDED.status,
  assigned_officer = EXCLUDED.assigned_officer,
  resolved_at = EXCLUDED.resolved_at,
  resolution_notes = EXCLUDED.resolution_notes;

INSERT INTO external_events (
  external_id, source, name, venue, location, event_date, event_time, end_time,
  estimated_crowd, category, raw_data, is_verified
) VALUES
  ('demo-jkt-001', 'manual', 'Jakarta Night Run 2026', 'Monas', ST_SetSRID(ST_MakePoint(106.8272, -6.1754), 4326)::geography, CURRENT_DATE + 3, '21:00:00', '23:30:00', 22000, 'sports', '{"organizer":"demo","traffic_note":"penutupan sebagian Jalan Medan Merdeka"}'::jsonb, true),
  ('demo-jkt-002', 'manual', 'Festival Kuliner Senayan', 'Senayan Park', ST_SetSRID(ST_MakePoint(106.8016, -6.2252), 4326)::geography, CURRENT_DATE + 5, '16:00:00', '22:00:00', 12000, 'fair', '{"organizer":"demo","traffic_note":"parkir penuh setelah 18:00"}'::jsonb, true),
  ('demo-jkt-003', 'manual', 'Konser Stadion Utama GBK', 'GBK', ST_SetSRID(ST_MakePoint(106.8018, -6.2183), 4326)::geography, CURRENT_DATE + 7, '19:00:00', '22:30:00', 80000, 'concert', '{"organizer":"demo","traffic_note":"lonjakan kendaraan area Asia Afrika"}'::jsonb, true)
ON CONFLICT (external_id) DO UPDATE SET
  source = EXCLUDED.source,
  name = EXCLUDED.name,
  venue = EXCLUDED.venue,
  location = EXCLUDED.location,
  event_date = EXCLUDED.event_date,
  event_time = EXCLUDED.event_time,
  end_time = EXCLUDED.end_time,
  estimated_crowd = EXCLUDED.estimated_crowd,
  category = EXCLUDED.category,
  raw_data = EXCLUDED.raw_data,
  is_verified = EXCLUDED.is_verified;

INSERT INTO event_predictions (
  id, event_id, event_name, impact_start, impact_end, affected_segments,
  mitigation_actions, confidence
) VALUES
  (
    '30000000-0000-0000-0000-000000000001',
    'evt-001',
    'Konser Coldplay Jakarta',
    ((CURRENT_DATE + 7) + TIME '16:00'),
    ((CURRENT_DATE + 7) + TIME '23:30'),
    '[
      {"segment_id":"gbk-asia-afrika","congestion_level":86,"coordinates":[[106.7979,-6.2205],[106.8071,-6.2210]]},
      {"segment_id":"senayan-sudirman","congestion_level":78,"coordinates":[[106.8015,-6.2251],[106.8162,-6.2149]]}
    ]'::jsonb,
    '[
      {"action":"Aktifkan rekayasa lalu lintas pintu 10 GBK","location":"Jl. Asia Afrika","priority":"high"},
      {"action":"Tambah petugas pengurai antrean parkir","location":"Senayan","priority":"medium"}
    ]'::jsonb,
    0.82
  )
ON CONFLICT (id) DO UPDATE SET
  event_id = EXCLUDED.event_id,
  event_name = EXCLUDED.event_name,
  impact_start = EXCLUDED.impact_start,
  impact_end = EXCLUDED.impact_end,
  affected_segments = EXCLUDED.affected_segments,
  mitigation_actions = EXCLUDED.mitigation_actions,
  confidence = EXCLUDED.confidence;

INSERT INTO daily_reports (
  report_date, total_incidents, by_type, by_severity, by_hour, top_locations,
  avg_response_time_s, resolved_count, pdf_url
) VALUES
  (
    CURRENT_DATE,
    5,
    '{"congestion":2,"illegal_parking":1,"busway_violation":1,"wrong_way":1}'::jsonb,
    '{"high":3,"medium":2,"low":0}'::jsonb,
    '{"7":1,"8":2,"17":1,"18":1}'::jsonb,
    '[
      {"lat":-6.2088,"lng":106.8228,"count":2,"type":"congestion"},
      {"lat":-6.1889,"lng":106.8156,"count":1,"type":"illegal_parking"}
    ]'::jsonb,
    2520,
    1,
    '/api/reports/daily/today'
  ),
  (
    CURRENT_DATE - 1,
    2,
    '{"illegal_parking":1,"hazard_lights":1}'::jsonb,
    '{"high":0,"medium":1,"low":1}'::jsonb,
    '{"13":1,"16":1}'::jsonb,
    '[
      {"lat":-6.1867,"lng":106.8226,"count":1,"type":"illegal_parking"},
      {"lat":-6.2365,"lng":106.8309,"count":1,"type":"hazard_lights"}
    ]'::jsonb,
    1800,
    2,
    NULL
  )
ON CONFLICT (report_date) DO UPDATE SET
  total_incidents = EXCLUDED.total_incidents,
  by_type = EXCLUDED.by_type,
  by_severity = EXCLUDED.by_severity,
  by_hour = EXCLUDED.by_hour,
  top_locations = EXCLUDED.top_locations,
  avg_response_time_s = EXCLUDED.avg_response_time_s,
  resolved_count = EXCLUDED.resolved_count,
  pdf_url = EXCLUDED.pdf_url,
  generated_at = NOW();

SELECT calculate_risk_zones();

DELETE FROM placement_recommendations
WHERE rationale LIKE '[DEMO]%';

INSERT INTO placement_recommendations (
  location, recommendation_type, priority_rank, risk_score, violation_types,
  coverage_radius_m, rationale, is_active
)
SELECT
  location,
  'camera_etle',
  ROW_NUMBER() OVER (ORDER BY risk_score DESC),
  risk_score,
  violation_types,
  150.0,
  '[DEMO] Pasang kamera E-TLE di titik dengan kepadatan insiden tertinggi.',
  true
FROM risk_zones
ORDER BY risk_score DESC
LIMIT 5;

INSERT INTO placement_recommendations (
  location, recommendation_type, priority_rank, risk_score, violation_types,
  coverage_radius_m, rationale, is_active
)
SELECT
  location,
  'officer',
  ROW_NUMBER() OVER (ORDER BY risk_score DESC),
  risk_score,
  violation_types,
  300.0,
  '[DEMO] Tempatkan petugas lapangan untuk respons cepat di jam rawan.',
  true
FROM risk_zones
ORDER BY risk_score DESC
LIMIT 5;

COMMIT;
