import os
import asyncpg
from fastapi import APIRouter
from app.models.schemas import Camera

router = APIRouter(prefix="/api/cameras", tags=["cameras"])

DUMMY_VIDEO_1 = "/api/uploads/angkot-parkir-sembarangan.mp4"
DUMMY_VIDEO_2 = "/api/uploads/motor-potong-lajur-mobil-dari-kanan-ke-kiri.mp4"

LOCAL_CAMERAS: list[Camera] = [
    # ---------- Dummy Cameras ----------
    Camera(
        id="cam-dummy-1",
        name="Dummy - Angkot Parkir",
        lat=-6.2000,
        lng=106.8166,
        stream_url=DUMMY_VIDEO_1,
    ),
    Camera(
        id="cam-dummy-2",
        name="Dummy - Motor Potong",
        lat=-6.2100,
        lng=106.8200,
        stream_url=DUMMY_VIDEO_2,
    ),
    # ---------- ESP32-S3 Live Dashcam ----------
    # ponytail: stream_url points to ESP32 directly (backend proxy reads from this)
    # Frontend <img> uses /ws/livecam/esp32-stream proxy endpoint instead
    Camera(
        id="esp32-dashcam",
        name="ESP32-S3 Dashcam (Live)",
        lat=-6.1754,
        lng=106.8272,
        stream_url="http://10.194.248.226/stream",
    ),
    # ---------- User's own cameras ----------
    # These use nearby Balitower public CCTV streams that are
    # confirmed accessible via embed.html (iframe) and index.m3u8 (HLS).
    Camera(
        id="cam-001",
        name="Bundaran HI",
        lat=-6.1944,
        lng=106.8229,
        stream_url="https://cctv.balitower.co.id/Menteng-Tenggulun-P01-507302_1/embed.html",
    ),
    Camera(
        id="cam-002",
        name="Semanggi",
        lat=-6.2088,
        lng=106.8228,
        stream_url="https://cctv.balitower.co.id/Senayan-004-705087_1/embed.html",
    ),
    Camera(
        id="cam-003",
        name="Blok M",
        lat=-6.2441,
        lng=106.7993,
        stream_url="https://cctv.balitower.co.id/Kuningan-Barat-003-705052_3/embed.html",
    ),
    Camera(
        id="cam-004",
        name="Sarinah",
        lat=-6.1867,
        lng=106.8226,
        stream_url="https://cctv.balitower.co.id/Tomang-004-702108_2/embed.html",
    ),
]

BALITOWER_CAMERAS: list[Camera] = [
    # Bendungan Hilir (4 cameras)
    Camera(
        id="bendungan-hilir-1",
        name="Bendungan Hilir 1",
        lat=-6.2150,
        lng=106.8220,
        stream_url="https://cctv.balitower.co.id/Bendungan-Hilir-003-700014_1/embed.html",
    ),
    Camera(
        id="bendungan-hilir-2",
        name="Bendungan Hilir 2",
        lat=-6.2145,
        lng=106.8225,
        stream_url="https://cctv.balitower.co.id/Bendungan-Hilir-003-700014_2/embed.html",
    ),
    Camera(
        id="bendungan-hilir-3",
        name="Bendungan Hilir 3",
        lat=-6.2155,
        lng=106.8215,
        stream_url="https://cctv.balitower.co.id/Bendungan-Hilir-003-700014_3/embed.html",
    ),
    Camera(
        id="bendungan-hilir-4",
        name="Bendungan Hilir 4",
        lat=-6.2140,
        lng=106.8230,
        stream_url="https://cctv.balitower.co.id/Bendungan-Hilir-003-700014_4/embed.html",
    ),
    # Gelora Bung Karno — GBK (9 cameras)
    Camera(
        id="gbk-1",
        name="GBK 1",
        lat=-6.2188,
        lng=106.8020,
        stream_url="https://cctv.balitower.co.id/Gelora-017-700470_2/embed.html",
    ),
    Camera(
        id="gbk-2",
        name="GBK 2",
        lat=-6.2183,
        lng=106.8015,
        stream_url="https://cctv.balitower.co.id/Gelora-017-700470_3/embed.html",
    ),
    Camera(
        id="gbk-3",
        name="GBK 3",
        lat=-6.2178,
        lng=106.8025,
        stream_url="https://cctv.balitower.co.id/Gelora-017-700470_4/embed.html",
    ),
    Camera(
        id="gbk-4",
        name="GBK 4",
        lat=-6.2193,
        lng=106.8010,
        stream_url="https://cctv.balitower.co.id/Gelora-017-700470_5/embed.html",
    ),
    Camera(
        id="gbk-5",
        name="GBK 5",
        lat=-6.2173,
        lng=106.8030,
        stream_url="https://cctv.balitower.co.id/Gelora-017-700470_6/embed.html",
    ),
    Camera(
        id="gbk-6",
        name="GBK 6",
        lat=-6.2180,
        lng=106.8005,
        stream_url="https://cctv.balitower.co.id/Gelora-017-700470_7/embed.html",
    ),
    Camera(
        id="gbk-7",
        name="GBK 7",
        lat=-6.2190,
        lng=106.8035,
        stream_url="https://cctv.balitower.co.id/Gelora-017-700470_8/embed.html",
    ),
    Camera(
        id="gbk-8",
        name="GBK 8",
        lat=-6.2170,
        lng=106.8010,
        stream_url="https://cctv.balitower.co.id/Gelora-017-700470_9/embed.html",
    ),
    Camera(
        id="gbk-9",
        name="GBK 9",
        lat=-6.2165,
        lng=106.8025,
        stream_url="https://cctv.balitower.co.id/Gelora-017-700470_10/embed.html",
    ),
    # GBK Jl. Asia Afrika (4 cameras)
    Camera(
        id="gbk-asia-afrika-1",
        name="GBK Jl. Asia Afrika 1",
        lat=-6.2210,
        lng=106.8005,
        stream_url="https://cctv.balitower.co.id/GBKC1002/embed.html",
    ),
    Camera(
        id="gbk-asia-afrika-2",
        name="GBK Jl. Asia Afrika 2",
        lat=-6.2215,
        lng=106.8010,
        stream_url="https://cctv.balitower.co.id/GBKC1003/embed.html",
    ),
    Camera(
        id="gbk-asia-afrika-3",
        name="GBK Jl. Asia Afrika 3",
        lat=-6.2220,
        lng=106.8000,
        stream_url="https://cctv.balitower.co.id/GBKC1004/embed.html",
    ),
    Camera(
        id="gbk-asia-afrika-4",
        name="GBK Jl. Asia Afrika 4",
        lat=-6.2225,
        lng=106.8015,
        stream_url="https://cctv.balitower.co.id/GBKC1005/embed.html",
    ),
    # Tanjung Duren (3 cameras)
    Camera(
        id="tanjung-duren-1",
        name="Tanjung Duren 1",
        lat=-6.1750,
        lng=106.7900,
        stream_url="https://cctv.balitower.co.id/Tanjung-Duren-Utara-005-702471_2/embed.html",
    ),
    Camera(
        id="tanjung-duren-2",
        name="Tanjung Duren 2",
        lat=-6.1745,
        lng=106.7905,
        stream_url="https://cctv.balitower.co.id/Tanjung-Duren-Utara-005-702471_3/embed.html",
    ),
    Camera(
        id="tanjung-duren-3",
        name="Tanjung Duren 3",
        lat=-6.1755,
        lng=106.7895,
        stream_url="https://cctv.balitower.co.id/Tanjung-Duren-Utara-005-702471_4/embed.html",
    ),
    # Tomang (2 cameras)
    Camera(
        id="tomang-1",
        name="Tomang 1",
        lat=-6.1710,
        lng=106.8040,
        stream_url="https://cctv.balitower.co.id/Tomang-004-702108_2/embed.html",
    ),
    Camera(
        id="tomang-2",
        name="Tomang 2",
        lat=-6.1715,
        lng=106.8035,
        stream_url="https://cctv.balitower.co.id/Tomang-004-702108_3/embed.html",
    ),
    # Jati Pulo (3 cameras)
    Camera(
        id="jati-pulo-1",
        name="Jati Pulo 1",
        lat=-6.1820,
        lng=106.8100,
        stream_url="https://cctv.balitower.co.id/Jati-Pulo-001-702017_2/embed.html",
    ),
    Camera(
        id="jati-pulo-2",
        name="Jati Pulo 2",
        lat=-6.1815,
        lng=106.8105,
        stream_url="https://cctv.balitower.co.id/Jati-Pulo-001-702017_3/embed.html",
    ),
    Camera(
        id="jati-pulo-3",
        name="Jati Pulo 3",
        lat=-6.1825,
        lng=106.8095,
        stream_url="https://cctv.balitower.co.id/Jati-Pulo-001-702017_4/embed.html",
    ),
    # Kemanggisan (2 cameras)
    Camera(
        id="kemanggisan-1",
        name="Kemanggisan 1",
        lat=-6.1850,
        lng=106.7880,
        stream_url="https://cctv.balitower.co.id/Kemanggisan-038-792405_2/embed.html",
    ),
    Camera(
        id="kemanggisan-2",
        name="Kemanggisan 2",
        lat=-6.1845,
        lng=106.7885,
        stream_url="https://cctv.balitower.co.id/Kemanggisan-038-792405_3/embed.html",
    ),
    # Menteng (3 cameras)
    Camera(
        id="menteng-1",
        name="Menteng 1",
        lat=-6.1950,
        lng=106.8350,
        stream_url="https://cctv.balitower.co.id/Menteng-Tenggulun-P01-507302_1/embed.html",
    ),
    Camera(
        id="menteng-2",
        name="Menteng 2",
        lat=-6.1945,
        lng=106.8355,
        stream_url="https://cctv.balitower.co.id/Menteng-Tenggulun-P01-507302_2/embed.html",
    ),
    Camera(
        id="menteng-3",
        name="Menteng 3",
        lat=-6.1955,
        lng=106.8345,
        stream_url="https://cctv.balitower.co.id/Menteng-Tenggulun-P01-507302_3/embed.html",
    ),
    # Pasar Manggis
    Camera(
        id="pasar-manggis",
        name="Pasar Manggis",
        lat=-6.2130,
        lng=106.8420,
        stream_url="https://cctv.balitower.co.id/Pasar-Manggis-014-795129_4/embed.html",
    ),
    # Senayan (4 cameras)
    Camera(
        id="senayan-1",
        name="Senayan 1",
        lat=-6.2240,
        lng=106.8030,
        stream_url="https://cctv.balitower.co.id/Senayan-004-705087_1/embed.html",
    ),
    Camera(
        id="senayan-2",
        name="Senayan 2",
        lat=-6.2245,
        lng=106.8025,
        stream_url="https://cctv.balitower.co.id/Senayan-004-705087_2/embed.html",
    ),
    Camera(
        id="senayan-3",
        name="Senayan 3",
        lat=-6.2235,
        lng=106.8035,
        stream_url="https://cctv.balitower.co.id/Senayan-004-705087_3/embed.html",
    ),
    Camera(
        id="senayan-4",
        name="Senayan 4",
        lat=-6.2240,
        lng=106.8020,
        stream_url="https://cctv.balitower.co.id/Senayan-004-705087_4/embed.html",
    ),
    # Kuningan Barat (2 cameras)
    Camera(
        id="kuningan-barat-1",
        name="Kuningan Barat 1",
        lat=-6.2400,
        lng=106.8180,
        stream_url="https://cctv.balitower.co.id/Kuningan-Barat-003-705052_3/embed.html",
    ),
    Camera(
        id="kuningan-barat-2",
        name="Kuningan Barat 2",
        lat=-6.2395,
        lng=106.8185,
        stream_url="https://cctv.balitower.co.id/Kuningan-Barat-003-705052_4/embed.html",
    ),
    # Cikoko (3 cameras)
    Camera(
        id="cikoko-1",
        name="Cikoko 1",
        lat=-6.2550,
        lng=106.8520,
        stream_url="https://cctv.balitower.co.id/Cikoko-006-705651_2/embed.html",
    ),
    Camera(
        id="cikoko-2",
        name="Cikoko 2",
        lat=-6.2545,
        lng=106.8525,
        stream_url="https://cctv.balitower.co.id/Cikoko-006-705651_3/embed.html",
    ),
    Camera(
        id="cikoko-3",
        name="Cikoko 3",
        lat=-6.2555,
        lng=106.8515,
        stream_url="https://cctv.balitower.co.id/Cikoko-006-705651_4/embed.html",
    ),
    # Cengkareng Barat
    Camera(
        id="cengkareng-barat",
        name="Cengkareng Barat 1",
        lat=-6.1450,
        lng=106.7300,
        stream_url="https://cctv.balitower.co.id/Cengkareng-Barat-013-702131_2/embed.html",
    ),
    # Manggarai Pintu Air (3 cameras)
    Camera(
        id="manggarai-pintu-air-1",
        name="Manggarai Pintu Air 1",
        lat=-6.2100,
        lng=106.8470,
        stream_url="https://cctv.balitower.co.id/Manggarai-Pintu-Air_1/embed.html?proto=hls",
    ),
    Camera(
        id="manggarai-pintu-air-2",
        name="Manggarai Pintu Air 2",
        lat=-6.2095,
        lng=106.8475,
        stream_url="https://cctv.balitower.co.id/Manggarai-Pintu-Air_2/embed.html?proto=hls",
    ),
    Camera(
        id="manggarai-pintu-air-3",
        name="Manggarai Pintu Air 3",
        lat=-6.2105,
        lng=106.8465,
        stream_url="https://cctv.balitower.co.id/Manggarai-Pintu-Air_3/embed.html?proto=hls",
    ),
]


@router.get("/", response_model=list[Camera])
async def get_cameras():
    try:
        conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
        try:
            rows = await conn.fetch(
                """
                SELECT id, name, ST_Y(location::geometry) as lat, ST_X(location::geometry) as lng, stream_url
                FROM cameras
                WHERE is_active = true
                ORDER BY id ASC
                """
            )
            if not rows:
                return LOCAL_CAMERAS + BALITOWER_CAMERAS
            
            db_cameras = [
                Camera(
                    id=row["id"],
                    name=row["name"],
                    lat=row["lat"],
                    lng=row["lng"],
                    stream_url=row["stream_url"]
                )
                for row in rows
            ]
            
            seen_ids = set()
            combined = []
            for cam in LOCAL_CAMERAS:
                if cam.id not in seen_ids:
                    seen_ids.add(cam.id)
                    combined.append(cam)
            for cam in db_cameras:
                if cam.id not in seen_ids:
                    seen_ids.add(cam.id)
                    combined.append(cam)
            return combined
        finally:
            await conn.close()
    except Exception as e:
        print(f"Error querying cameras from database: {e}")
        return LOCAL_CAMERAS + BALITOWER_CAMERAS
