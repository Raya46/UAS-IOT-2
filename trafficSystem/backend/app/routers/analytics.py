from fastapi import APIRouter, Query
from typing import Optional
import asyncpg
import os
from datetime import datetime, date, timedelta

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

@router.get("/heatmap")
async def get_heatmap_data(
    days: int = Query(30, ge=1, le=90),
    hour_from: int = Query(0, ge=0, le=23),
    hour_to: int = Query(23, ge=0, le=23),
    day_of_week: Optional[int] = Query(None, ge=0, le=6),  # 0=Senin, 6=Minggu (wait, postgis DOW is 0=Minggu, 6=Sabtu)
    violation_type: Optional[str] = Query(None),
):
    """Data heatmap untuk Mapbox GL JS heatmap layer."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        params = [days, hour_from, hour_to]
        where = [
            "occurred_at >= NOW() - $1 * INTERVAL '1 day'",
            "hour_of_day >= $2",
            "hour_of_day <= $3",
        ]
        idx = 4

        if day_of_week is not None:
            where.append(f"day_of_week = ${idx}")
            params.append(day_of_week)
            idx += 1

        if violation_type:
            where.append(f"type = ${idx}")
            params.append(violation_type)
            idx += 1

        where_sql = " AND ".join(where)

        rows = await conn.fetch(
            f"""
            SELECT lat, lng, type, severity, COUNT(*) as weight
            FROM violation_heatmap_data
            WHERE {where_sql}
            GROUP BY lat, lng, type, severity
            """,
            *params,
        )

        # Format GeoJSON FeatureCollection untuk Mapbox heatmap layer
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row["lng"], row["lat"]]},
                "properties": {
                    "weight": row["weight"],
                    "type": row["type"],
                    "severity": row["severity"],
                },
            }
            for row in rows
        ]

        return {
            "type": "FeatureCollection",
            "features": features,
            "meta": {"total_points": len(features), "days": days}
        }
    finally:
        await conn.close()

@router.get("/stats/by-hour")
async def get_stats_by_hour(days: int = Query(30, ge=1, le=90)):
    """Distribusi pelanggaran per jam untuk chart di Executive Summary."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        rows = await conn.fetch(
            """
            SELECT EXTRACT(HOUR FROM occurred_at)::INTEGER as hour,
                   COUNT(*) as count,
                   type
            FROM incidents
            WHERE occurred_at >= NOW() - $1 * INTERVAL '1 day'
            GROUP BY hour, type
            ORDER BY hour
            """,
            days,
        )
        result: dict[int, dict] = {h: {} for h in range(24)}
        for row in rows:
            result[row["hour"]][row["type"]] = row["count"]
        return result
    finally:
        await conn.close()

@router.get("/stats/summary")
async def get_summary_stats(days: int = Query(7, ge=1, le=90)):
    """Statistik ringkasan untuk Executive Summary panel."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                                          AS total_incidents,
                COUNT(*) FILTER (WHERE severity = 'high')        AS high_severity,
                COUNT(*) FILTER (WHERE status = 'resolved')      AS resolved,
                AVG(confidence_score)                             AS avg_confidence,
                COUNT(DISTINCT DATE(occurred_at))                 AS active_days,
                EXTRACT(EPOCH FROM AVG(resolved_at - occurred_at))::INTEGER AS avg_response_s
            FROM incidents
            WHERE occurred_at >= NOW() - $1 * INTERVAL '1 day'
            """,
            days,
        )

        by_type = await conn.fetch(
            """
            SELECT type, COUNT(*) as count
            FROM incidents
            WHERE occurred_at >= NOW() - $1 * INTERVAL '1 day'
            GROUP BY type ORDER BY count DESC
            """,
            days,
        )

        return {
            "total_incidents": row["total_incidents"] or 0,
            "high_severity": row["high_severity"] or 0,
            "resolved": row["resolved"] or 0,
            "avg_confidence": round(float(row["avg_confidence"] or 0), 2),
            "avg_response_seconds": row["avg_response_s"] or 0,
            "by_type": {r["type"]: r["count"] for r in by_type},
        }
    finally:
        await conn.close()

@router.get("/risk-zones")
async def get_risk_zones():
    """Titik rawan hasil kalkulasi risk profiling."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        rows = await conn.fetch(
            """
            SELECT
                ST_Y(location::geometry) AS lat,
                ST_X(location::geometry) AS lng,
                risk_score,
                violation_types,
                incident_count,
                peak_hours
            FROM risk_zones
            ORDER BY risk_score DESC
            LIMIT 100
            """
        )

        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row["lng"], row["lat"]]},
                "properties": {
                    "risk_score": row["risk_score"],
                    "violation_types": list(row["violation_types"] or []),
                    "incident_count": row["incident_count"],
                    "peak_hours": list(row["peak_hours"] or []),
                    "weight": row["risk_score"],
                },
            }
            for row in rows
        ]

        return {"type": "FeatureCollection", "features": features}
    finally:
        await conn.close()

@router.post("/risk-zones/recalculate")
async def recalculate_risk_zones():
    """
    Trigger kalkulasi ulang risk zones. Panggil dari scheduler harian (misal jam 02:00 WIB).
    Atau panggil manual dari admin panel.
    """
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        await conn.execute("SELECT calculate_risk_zones()")
        count = await conn.fetchval("SELECT COUNT(*) FROM risk_zones")
        return {"success": True, "risk_zones_count": count}
    finally:
        await conn.close()
