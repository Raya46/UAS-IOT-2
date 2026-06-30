from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import asyncpg
import os
import json
import uuid
from datetime import datetime, timezone
from app.models.schemas import IncidentCreatePayload, IncidentPayload, IncidentStatusUpdate, IncidentListResponse
from app.services.redis_client import get_redis

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

_metadata_columns_ready = False


async def ensure_incident_metadata_columns(conn):
    """Keep local demo DBs compatible with newer evidence metadata fields."""
    global _metadata_columns_ready
    if _metadata_columns_ready:
        return

    await conn.execute(
        """
        ALTER TABLE incidents
          ADD COLUMN IF NOT EXISTS description TEXT,
          ADD COLUMN IF NOT EXISTS vehicle_type VARCHAR(80),
          ADD COLUMN IF NOT EXISTS plate_number VARCHAR(40),
          ADD COLUMN IF NOT EXISTS plate_crop TEXT,
          ADD COLUMN IF NOT EXISTS plate_bbox JSONB,
          ADD COLUMN IF NOT EXISTS plate_confidence FLOAT,
          ADD COLUMN IF NOT EXISTS plate_note TEXT,
          ADD COLUMN IF NOT EXISTS video_time_seconds FLOAT
        """
    )
    _metadata_columns_ready = True


def incident_uuid_from_payload_id(payload_id: Optional[str]) -> uuid.UUID:
    if not payload_id:
        return uuid.uuid4()
    try:
        return uuid.UUID(payload_id)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"artery:incident:{payload_id}")


def parse_incident_timestamp(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


async def ensure_camera_for_incident(conn, payload: IncidentCreatePayload) -> Optional[str]:
    if not payload.camera_id:
        return None

    camera_id = payload.camera_id[:50]
    camera_name = (payload.camera_name or payload.camera_id)[:200]
    await conn.execute(
        """
        INSERT INTO cameras (id, name, location, stream_url, is_active)
        VALUES ($1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography, NULL, true)
        ON CONFLICT (id) DO UPDATE SET
          name = COALESCE(cameras.name, EXCLUDED.name),
          location = COALESCE(cameras.location, EXCLUDED.location),
          is_active = true
        """,
        camera_id,
        camera_name,
        payload.lng,
        payload.lat,
    )
    return camera_id


def row_to_incident_payload(row) -> IncidentPayload:
    data = dict(row)
    plate_bbox = data.get("plate_bbox")
    if isinstance(plate_bbox, str):
        try:
            plate_bbox = json.loads(plate_bbox)
        except json.JSONDecodeError:
            plate_bbox = None
    return IncidentPayload(
        id=str(data["id"]),
        camera_id=data["camera_id"] or "",
        type=data["type"],
        lat=data["lat"],
        lng=data["lng"],
        severity=data["severity"],
        confidence_score=data["confidence_score"],
        source_count=data["source_count"],
        status=data["status"],
        timestamp=data["occurred_at"].isoformat(),
        snapshot_url=data["snapshot_url"],
        description=data.get("description") or data.get("title"),
        vehicle_type=data.get("vehicle_type"),
        plate_number=data.get("plate_number"),
        plate_crop=data.get("plate_crop"),
        plate_bbox=plate_bbox,
        plate_confidence=data.get("plate_confidence"),
        plate_note=data.get("plate_note"),
        video_time_seconds=data.get("video_time_seconds"),
    )

async def get_db():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        yield conn
    finally:
        await conn.close()

@router.get("/", response_model=IncidentListResponse)
async def list_incidents(
    status: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Daftar incidents dengan filter dan pagination."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        await ensure_incident_metadata_columns(conn)
        where_clauses = []
        params = []
        idx = 1

        if status:
            where_clauses.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        if type:
            where_clauses.append(f"type = ${idx}")
            params.append(type)
            idx += 1

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        offset = (page - 1) * page_size

        total = await conn.fetchval(f"SELECT COUNT(*) FROM incidents {where_sql}", *params)

        rows = await conn.fetch(
            f"""
            SELECT id, title, camera_id, type, severity, confidence_score, source_count,
                   status, assigned_officer, snapshot_url,
                   description, vehicle_type, plate_number, plate_crop, plate_bbox,
                   plate_confidence, plate_note, video_time_seconds,
                   ST_Y(location::geometry) as lat, ST_X(location::geometry) as lng,
                   occurred_at
            FROM incidents {where_sql}
            ORDER BY occurred_at DESC
            LIMIT {page_size} OFFSET {offset}
            """,
            *params
        )

        items = [row_to_incident_payload(row) for row in rows]
        return IncidentListResponse(items=items, total=total, page=page, page_size=page_size)
    finally:
        await conn.close()


@router.post("/", response_model=IncidentPayload)
async def create_incident(payload: IncidentCreatePayload):
    """Create or upsert a simulated/live incident as a real DB incident."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        await ensure_incident_metadata_columns(conn)
        incident_id = incident_uuid_from_payload_id(payload.id)
        occurred_at = parse_incident_timestamp(payload.timestamp)
        now = datetime.now(timezone.utc)
        camera_id = await ensure_camera_for_incident(conn, payload)
        title = payload.description or f"Deteksi {payload.type.replace('_', ' ')}"

        row = await conn.fetchrow(
            """
            INSERT INTO incidents (
              id, title, type, location, severity, confidence_score, status,
              source_count, snapshot_url, camera_id, occurred_at, updated_at,
              description, vehicle_type, plate_number, plate_crop, plate_bbox,
              plate_confidence, plate_note, video_time_seconds
            )
            VALUES (
              $1::uuid, $2, $3, ST_SetSRID(ST_MakePoint($4, $5), 4326)::geography,
              $6, $7, $8, $9, $10, $11, $12, $13,
              $14, $15, $16, $17, $18::jsonb, $19, $20, $21
            )
            ON CONFLICT (id) DO UPDATE SET
              title = EXCLUDED.title,
              type = EXCLUDED.type,
              location = EXCLUDED.location,
              severity = EXCLUDED.severity,
              confidence_score = EXCLUDED.confidence_score,
              status = EXCLUDED.status,
              source_count = EXCLUDED.source_count,
              snapshot_url = EXCLUDED.snapshot_url,
              camera_id = EXCLUDED.camera_id,
              occurred_at = EXCLUDED.occurred_at,
              updated_at = EXCLUDED.updated_at,
              description = EXCLUDED.description,
              vehicle_type = EXCLUDED.vehicle_type,
              plate_number = EXCLUDED.plate_number,
              plate_crop = EXCLUDED.plate_crop,
              plate_bbox = EXCLUDED.plate_bbox,
              plate_confidence = EXCLUDED.plate_confidence,
              plate_note = EXCLUDED.plate_note,
              video_time_seconds = EXCLUDED.video_time_seconds
            RETURNING id, title, camera_id, type, severity, confidence_score, source_count,
                      status, snapshot_url, description, vehicle_type, plate_number,
                      plate_crop, plate_bbox, plate_confidence, plate_note, video_time_seconds,
                      ST_Y(location::geometry) as lat, ST_X(location::geometry) as lng,
                      occurred_at
            """,
            incident_id,
            title,
            payload.type,
            payload.lng,
            payload.lat,
            payload.severity,
            payload.confidence_score,
            payload.status,
            payload.source_count,
            payload.snapshot_url,
            camera_id,
            occurred_at,
            now,
            payload.description,
            payload.vehicle_type,
            payload.plate_number,
            payload.plate_crop,
            json.dumps(payload.plate_bbox) if payload.plate_bbox else None,
            payload.plate_confidence,
            payload.plate_note,
            payload.video_time_seconds,
        )

        incident = row_to_incident_payload(row)
        if payload.broadcast:
            redis = get_redis()
            incident_dict = incident.model_dump() if hasattr(incident, "model_dump") else incident.dict()
            redis.publish("traffic.incident_update", json.dumps({
                "type": "incident",
                "payload": incident_dict,
            }))
        return incident
    finally:
        await conn.close()

@router.patch("/{incident_id}/status")
async def update_incident_status(incident_id: str, update: IncidentStatusUpdate):
    """Update status lifecycle sebuah incident. Publish ke WebSocket setelah update."""
    try:
        incident_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Incident tidak ditemukan")

    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        now = datetime.now(timezone.utc)
        resolved_at = now if update.status in ("resolved", "closed") else None

        result = await conn.execute(
            """
            UPDATE incidents SET
                status = $1::varchar,
                assigned_officer = COALESCE($2::varchar, assigned_officer),
                assigned_at = CASE WHEN $1::varchar = 'dispatched' THEN $4 ELSE assigned_at END,
                resolved_at = COALESCE($3, resolved_at),
                resolution_notes = COALESCE($5, resolution_notes),
                updated_at = $4
            WHERE id = $6::uuid
            """,
            update.status,
            update.assigned_officer,
            resolved_at,
            now,
            update.resolution_notes,
            incident_uuid,
        )

        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Incident tidak ditemukan")

        # Broadcast status update ke semua client WebSocket
        redis = get_redis()
        redis.publish("traffic.incident_update", json.dumps({
            "type": "incident_status_change",
            "payload": {
                "incident_id": incident_id,
                "status": update.status,
                "assigned_officer": update.assigned_officer,
                "updated_at": now.isoformat(),
            }
        }))

        return {"success": True, "incident_id": incident_id, "new_status": update.status}
    finally:
        await conn.close()

@router.get("/{incident_id}")
async def get_incident_detail(incident_id: str):
    """Detail lengkap satu incident termasuk timeline status."""
    try:
        incident_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Incident tidak ditemukan")

    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        await ensure_incident_metadata_columns(conn)
        row = await conn.fetchrow(
            """
            SELECT id, camera_id, type, severity, confidence_score, source_count,
                   status, assigned_officer, assigned_at, resolved_at, resolution_notes,
                   title, snapshot_url, description, vehicle_type, plate_number,
                   plate_crop, plate_bbox, plate_confidence, plate_note, video_time_seconds,
                   occurred_at, updated_at,
                   ST_Y(location::geometry) as lat, ST_X(location::geometry) as lng
            FROM incidents WHERE id = $1::uuid
            """,
            incident_uuid,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident tidak ditemukan")
        
        # Convert record to dictionary, turning datetime and UUID fields to serializable formats
        res = dict(row)
        res["id"] = str(res["id"])
        if res["assigned_at"]:
            res["assigned_at"] = res["assigned_at"].isoformat()
        if res["resolved_at"]:
            res["resolved_at"] = res["resolved_at"].isoformat()
        res["occurred_at"] = res["occurred_at"].isoformat()
        res["updated_at"] = res["updated_at"].isoformat()
        if isinstance(res.get("plate_bbox"), str):
            try:
                res["plate_bbox"] = json.loads(res["plate_bbox"])
            except json.JSONDecodeError:
                res["plate_bbox"] = None
        if not res.get("description"):
            res["description"] = res.get("title")
        return res
    finally:
        await conn.close()
