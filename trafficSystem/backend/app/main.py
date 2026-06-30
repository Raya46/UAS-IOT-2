import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import asyncpg

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.services.event_scraper import scrape_and_store_events
from app.routers.websocket import redis_listener
from app.routers import (
    cameras,
    zones,
    events,
    websocket,
    incidents,
    analytics,
    simulator,
    reports,
    cctv_data,
    livecam,
    violations,
    upload,
    dashcam,
    email,
)

load_dotenv()

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Jalankan Redis listener sebagai background task
    redis_task = asyncio.create_task(redis_listener())

    # Jadwal scraping event — setiap hari jam 03:00 WIB
    scheduler.add_job(scrape_and_store_events, "cron", hour=3, minute=0)

    # Jadwal kalkulasi risk zones — setiap hari jam 02:00 WIB
    async def recalc_risk():
        conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
        try:
            await conn.execute("SELECT calculate_risk_zones()")
        finally:
            await conn.close()

    # Jalankan sekali di awal saat startup agar data langsung terpopulasi
    try:
        await recalc_risk()
    except Exception as e:
        print(f"Error during startup risk zone calculation: {e}")

    scheduler.add_job(recalc_risk, "cron", hour=2, minute=0)
    scheduler.start()

    yield

    redis_task.cancel()
    scheduler.shutdown()


app = FastAPI(title="Traffic Dashboard API", lifespan=lifespan)

origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"
    ).split(",")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cameras.router)
app.include_router(zones.router)
app.include_router(events.router)
app.include_router(websocket.router)
app.include_router(incidents.router)
app.include_router(analytics.router)
app.include_router(simulator.router)
app.include_router(reports.router)
app.include_router(cctv_data.router)
app.include_router(livecam.router)
app.include_router(violations.router)
app.include_router(upload.router)
app.include_router(dashcam.router)
app.include_router(email.router)

from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve frontend static files
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
local_static_dir = os.path.join(root_dir, "frontend", "dist")
static_dir = os.getenv("STATIC_DIR", local_static_dir)

if os.path.exists(static_dir):
    assets_dir = os.path.join(static_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# Serve video uploads for dummy CCTV points
uploads_dir = os.path.join(root_dir, "backend", "data", "uploads")
if os.path.exists(uploads_dir):
    app.mount("/api/uploads", StaticFiles(directory=uploads_dir), name="uploads")

    @app.get("/{path_name:path}")
    async def catch_all(path_name: str):
        # Skip API and WS routes
        if path_name.startswith("api/") or path_name.startswith("ws"):
            return HTMLResponse(status_code=404)

        file_path = os.path.join(static_dir, path_name)
        if os.path.isfile(file_path):
            return FileResponse(file_path)

        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)

        return HTMLResponse("Frontend build not found.", status_code=404)
