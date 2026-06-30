import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.redis_client import get_redis
from app.services.incident_aggregator import process_violation
from app.models.schemas import Violation, IncidentPayload

router = APIRouter()

# Menyimpan semua koneksi WebSocket yang aktif
active_connections: list[WebSocket] = []

# Topic Redis yang didengarkan backend
SUBSCRIBED_TOPICS = [
    "traffic.violation",       # masuk dari CV worker (raw)
    "traffic.incident_update", # update confidence dari aggregator
    "traffic.congestion",
    "traffic.alert",
    "traffic.event_prediction",
]

async def broadcast(message: str):
    """Kirim pesan ke semua client yang sedang terhubung."""
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_text(message)
        except Exception:
            disconnected.append(connection)
    for conn in disconnected:
        active_connections.remove(conn)

async def redis_listener():
    """Background task: subscribe ke Redis dan forward semua pesan ke WebSocket.
    Uses sync redis pubsub in a thread executor to avoid blocking the event loop.
    """
    redis = get_redis()
    pubsub = redis.pubsub()
    pubsub.subscribe(*SUBSCRIBED_TOPICS)

    loop = asyncio.get_event_loop()

    while True:
        # Poll for messages using run_in_executor (non-blocking)
        message = await loop.run_in_executor(None, lambda: pubsub.get_message(timeout=1.0))
        if message is None or message["type"] != "message":
            await asyncio.sleep(0.05)
            continue

        raw = message["data"]
        try:
            parsed = json.loads(raw)
        except Exception:
            continue

        # Proses violation melalui aggregator
        if parsed.get("type") == "violation" and parsed.get("payload"):
            violation = Violation(**parsed["payload"])
            consolidated = await process_violation(violation)
            if consolidated is None:
                continue  # duplikat, skip
            # Publish incident terkonsolidasi sebagai event baru
            broadcast_msg = json.dumps({
                "type": "incident",
                "payload": consolidated.model_dump()
            })
            await broadcast(broadcast_msg)
        else:
            # Tipe lain (congestion, alert, dll) langsung broadcast
            await broadcast(raw)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # Tetap jaga koneksi terbuka, data dikirim dari redis_listener
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)
