-- ============================================================
-- Seed Balitower CCTV cameras into the database
-- Updates existing broken cameras + inserts all Balitower cameras
-- ============================================================

BEGIN;

-- 1) Update existing 4 cameras with working Balitower CCTV URLs
UPDATE cameras SET stream_url = 'https://cctv.balitower.co.id/Menteng-Tenggulun-P01-507302_1/embed.html' WHERE id = 'cam-001';
UPDATE cameras SET stream_url = 'https://cctv.balitower.co.id/Senayan-004-705087_1/embed.html' WHERE id = 'cam-002';
UPDATE cameras SET stream_url = 'https://cctv.balitower.co.id/Kuningan-Barat-003-705052_3/embed.html' WHERE id = 'cam-003';
UPDATE cameras SET stream_url = 'https://cctv.balitower.co.id/Tomang-004-702108_2/embed.html' WHERE id = 'cam-004';

-- 2) Insert all Balitower CCTV cameras (skip if already exists)

-- Bendungan Hilir (4 cameras)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('bendungan-hilir-1', 'Bendungan Hilir 1', ST_SetSRID(ST_MakePoint(106.8220, -6.2150), 4326)::geography, 'https://cctv.balitower.co.id/Bendungan-Hilir-003-700014_1/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('bendungan-hilir-2', 'Bendungan Hilir 2', ST_SetSRID(ST_MakePoint(106.8225, -6.2145), 4326)::geography, 'https://cctv.balitower.co.id/Bendungan-Hilir-003-700014_2/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('bendungan-hilir-3', 'Bendungan Hilir 3', ST_SetSRID(ST_MakePoint(106.8215, -6.2155), 4326)::geography, 'https://cctv.balitower.co.id/Bendungan-Hilir-003-700014_3/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('bendungan-hilir-4', 'Bendungan Hilir 4', ST_SetSRID(ST_MakePoint(106.8230, -6.2140), 4326)::geography, 'https://cctv.balitower.co.id/Bendungan-Hilir-003-700014_4/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

-- Gelora Bung Karno / GBK (9 cameras)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('gbk-1', 'GBK 1', ST_SetSRID(ST_MakePoint(106.8020, -6.2188), 4326)::geography, 'https://cctv.balitower.co.id/Gelora-017-700470_2/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('gbk-2', 'GBK 2', ST_SetSRID(ST_MakePoint(106.8015, -6.2183), 4326)::geography, 'https://cctv.balitower.co.id/Gelora-017-700470_3/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('gbk-3', 'GBK 3', ST_SetSRID(ST_MakePoint(106.8025, -6.2178), 4326)::geography, 'https://cctv.balitower.co.id/Gelora-017-700470_4/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('gbk-4', 'GBK 4', ST_SetSRID(ST_MakePoint(106.8010, -6.2193), 4326)::geography, 'https://cctv.balitower.co.id/Gelora-017-700470_5/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('gbk-5', 'GBK 5', ST_SetSRID(ST_MakePoint(106.8030, -6.2173), 4326)::geography, 'https://cctv.balitower.co.id/Gelora-017-700470_6/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('gbk-6', 'GBK 6', ST_SetSRID(ST_MakePoint(106.8005, -6.2180), 4326)::geography, 'https://cctv.balitower.co.id/Gelora-017-700470_7/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('gbk-7', 'GBK 7', ST_SetSRID(ST_MakePoint(106.8035, -6.2190), 4326)::geography, 'https://cctv.balitower.co.id/Gelora-017-700470_8/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('gbk-8', 'GBK 8', ST_SetSRID(ST_MakePoint(106.8010, -6.2170), 4326)::geography, 'https://cctv.balitower.co.id/Gelora-017-700470_9/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('gbk-9', 'GBK 9', ST_SetSRID(ST_MakePoint(106.8025, -6.2165), 4326)::geography, 'https://cctv.balitower.co.id/Gelora-017-700470_10/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

-- GBK Jl. Asia Afrika (4 cameras)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('gbk-asia-afrika-1', 'GBK Jl. Asia Afrika 1', ST_SetSRID(ST_MakePoint(106.8005, -6.2210), 4326)::geography, 'https://cctv.balitower.co.id/GBKC1002/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('gbk-asia-afrika-2', 'GBK Jl. Asia Afrika 2', ST_SetSRID(ST_MakePoint(106.8010, -6.2215), 4326)::geography, 'https://cctv.balitower.co.id/GBKC1003/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('gbk-asia-afrika-3', 'GBK Jl. Asia Afrika 3', ST_SetSRID(ST_MakePoint(106.8000, -6.2220), 4326)::geography, 'https://cctv.balitower.co.id/GBKC1004/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('gbk-asia-afrika-4', 'GBK Jl. Asia Afrika 4', ST_SetSRID(ST_MakePoint(106.8015, -6.2225), 4326)::geography, 'https://cctv.balitower.co.id/GBKC1005/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

-- Tanjung Duren (3 cameras)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('tanjung-duren-1', 'Tanjung Duren 1', ST_SetSRID(ST_MakePoint(106.7900, -6.1750), 4326)::geography, 'https://cctv.balitower.co.id/Tanjung-Duren-Utara-005-702471_2/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('tanjung-duren-2', 'Tanjung Duren 2', ST_SetSRID(ST_MakePoint(106.7905, -6.1745), 4326)::geography, 'https://cctv.balitower.co.id/Tanjung-Duren-Utara-005-702471_3/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('tanjung-duren-3', 'Tanjung Duren 3', ST_SetSRID(ST_MakePoint(106.7895, -6.1755), 4326)::geography, 'https://cctv.balitower.co.id/Tanjung-Duren-Utara-005-702471_4/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

-- Tomang (2 cameras)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('tomang-1', 'Tomang 1', ST_SetSRID(ST_MakePoint(106.8040, -6.1710), 4326)::geography, 'https://cctv.balitower.co.id/Tomang-004-702108_2/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('tomang-2', 'Tomang 2', ST_SetSRID(ST_MakePoint(106.8035, -6.1715), 4326)::geography, 'https://cctv.balitower.co.id/Tomang-004-702108_3/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

-- Jati Pulo (3 cameras)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('jati-pulo-1', 'Jati Pulo 1', ST_SetSRID(ST_MakePoint(106.8100, -6.1820), 4326)::geography, 'https://cctv.balitower.co.id/Jati-Pulo-001-702017_2/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('jati-pulo-2', 'Jati Pulo 2', ST_SetSRID(ST_MakePoint(106.8105, -6.1815), 4326)::geography, 'https://cctv.balitower.co.id/Jati-Pulo-001-702017_3/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('jati-pulo-3', 'Jati Pulo 3', ST_SetSRID(ST_MakePoint(106.8095, -6.1825), 4326)::geography, 'https://cctv.balitower.co.id/Jati-Pulo-001-702017_4/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

-- Kemanggisan (2 cameras)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('kemanggisan-1', 'Kemanggisan 1', ST_SetSRID(ST_MakePoint(106.7880, -6.1850), 4326)::geography, 'https://cctv.balitower.co.id/Kemanggisan-038-792405_2/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('kemanggisan-2', 'Kemanggisan 2', ST_SetSRID(ST_MakePoint(106.7885, -6.1845), 4326)::geography, 'https://cctv.balitower.co.id/Kemanggisan-038-792405_3/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

-- Menteng (3 cameras)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('menteng-1', 'Menteng 1', ST_SetSRID(ST_MakePoint(106.8350, -6.1950), 4326)::geography, 'https://cctv.balitower.co.id/Menteng-Tenggulun-P01-507302_1/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('menteng-2', 'Menteng 2', ST_SetSRID(ST_MakePoint(106.8355, -6.1945), 4326)::geography, 'https://cctv.balitower.co.id/Menteng-Tenggulun-P01-507302_2/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('menteng-3', 'Menteng 3', ST_SetSRID(ST_MakePoint(106.8345, -6.1955), 4326)::geography, 'https://cctv.balitower.co.id/Menteng-Tenggulun-P01-507302_3/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

-- Pasar Manggis (1 camera)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('pasar-manggis', 'Pasar Manggis', ST_SetSRID(ST_MakePoint(106.8420, -6.2130), 4326)::geography, 'https://cctv.balitower.co.id/Pasar-Manggis-014-795129_4/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

-- Senayan (4 cameras)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('senayan-1', 'Senayan 1', ST_SetSRID(ST_MakePoint(106.8030, -6.2240), 4326)::geography, 'https://cctv.balitower.co.id/Senayan-004-705087_1/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('senayan-2', 'Senayan 2', ST_SetSRID(ST_MakePoint(106.8025, -6.2245), 4326)::geography, 'https://cctv.balitower.co.id/Senayan-004-705087_2/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('senayan-3', 'Senayan 3', ST_SetSRID(ST_MakePoint(106.8035, -6.2235), 4326)::geography, 'https://cctv.balitower.co.id/Senayan-004-705087_3/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('senayan-4', 'Senayan 4', ST_SetSRID(ST_MakePoint(106.8020, -6.2240), 4326)::geography, 'https://cctv.balitower.co.id/Senayan-004-705087_4/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

-- Kuningan Barat (2 cameras)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('kuningan-barat-1', 'Kuningan Barat 1', ST_SetSRID(ST_MakePoint(106.8180, -6.2400), 4326)::geography, 'https://cctv.balitower.co.id/Kuningan-Barat-003-705052_3/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('kuningan-barat-2', 'Kuningan Barat 2', ST_SetSRID(ST_MakePoint(106.8185, -6.2395), 4326)::geography, 'https://cctv.balitower.co.id/Kuningan-Barat-003-705052_4/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

-- Cikoko (3 cameras)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('cikoko-1', 'Cikoko 1', ST_SetSRID(ST_MakePoint(106.8520, -6.2550), 4326)::geography, 'https://cctv.balitower.co.id/Cikoko-006-705651_2/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('cikoko-2', 'Cikoko 2', ST_SetSRID(ST_MakePoint(106.8525, -6.2545), 4326)::geography, 'https://cctv.balitower.co.id/Cikoko-006-705651_3/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('cikoko-3', 'Cikoko 3', ST_SetSRID(ST_MakePoint(106.8515, -6.2555), 4326)::geography, 'https://cctv.balitower.co.id/Cikoko-006-705651_4/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

-- Cengkareng Barat (1 camera)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('cengkareng-barat', 'Cengkareng Barat 1', ST_SetSRID(ST_MakePoint(106.7300, -6.1450), 4326)::geography, 'https://cctv.balitower.co.id/Cengkareng-Barat-013-702131_2/embed.html', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

-- Manggarai Pintu Air (3 cameras)
INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('manggarai-pintu-air-1', 'Manggarai Pintu Air 1', ST_SetSRID(ST_MakePoint(106.8470, -6.2100), 4326)::geography, 'https://cctv.balitower.co.id/Manggarai-Pintu-Air_1/embed.html?proto=hls', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('manggarai-pintu-air-2', 'Manggarai Pintu Air 2', ST_SetSRID(ST_MakePoint(106.8475, -6.2095), 4326)::geography, 'https://cctv.balitower.co.id/Manggarai-Pintu-Air_2/embed.html?proto=hls', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

INSERT INTO cameras (id, name, location, stream_url, is_active) VALUES
('manggarai-pintu-air-3', 'Manggarai Pintu Air 3', ST_SetSRID(ST_MakePoint(106.8465, -6.2105), 4326)::geography, 'https://cctv.balitower.co.id/Manggarai-Pintu-Air_3/embed.html?proto=hls', true)
ON CONFLICT (id) DO UPDATE SET stream_url = EXCLUDED.stream_url, name = EXCLUDED.name, is_active = true;

COMMIT;
