import asyncpg
import os
from typing import Literal

async def calculate_placements(
    placement_type: Literal["camera_etle", "officer"],
    top_n: int = 10,
) -> list[dict]:
    """
    Hitung rekomendasi titik penempatan berdasarkan risk_zones.
    Harus dijalankan setelah calculate_risk_zones() berjalan.
    """
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
                peak_hours,
                peak_days,
                radius_m
            FROM risk_zones
            ORDER BY risk_score DESC
            LIMIT $1
            """,
            top_n,
        )

        results = []
        for rank, row in enumerate(rows, start=1):
            v_types = list(row["violation_types"] or [])
            peak_hours = list(row["peak_hours"] or [])

            # Buat rationale berdasarkan data
            hour_desc = ""
            if peak_hours:
                peak_hours_sorted = sorted(peak_hours)
                hour_desc = f"puncak jam {peak_hours_sorted[0]:02d}:00–{peak_hours_sorted[-1]:02d}:00"

            rationale = (
                f"Titik dengan {row['incident_count']} insiden dalam 30 hari. "
                f"Dominan: {', '.join(v_types)}. {hour_desc}. "
                f"Risk score: {row['risk_score']:.2f}."
            )

            # Tentukan coverage radius berdasarkan tipe
            coverage = 150.0 if placement_type == "camera_etle" else 300.0

            results.append({
                "location": {"lat": row["lat"], "lng": row["lng"]},
                "recommendation_type": placement_type,
                "priority_rank": rank,
                "risk_score": row["risk_score"],
                "violation_types": v_types,
                "coverage_radius_m": coverage,
                "rationale": rationale,
                "peak_hours": peak_hours,
            })

        return results
    finally:
        await conn.close()
