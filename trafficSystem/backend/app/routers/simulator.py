from fastapi import APIRouter, Query
from typing import Literal
from app.services.placement_calculator import calculate_placements

router = APIRouter(prefix="/api/simulator", tags=["simulator"])

@router.get("/placements")
async def get_placement_recommendations(
    type: Literal["camera_etle", "officer"] = Query("camera_etle"),
    top_n: int = Query(10, ge=1, le=50),
):
    """
    Rekomendasi titik penempatan E-TLE atau petugas lapangan.
    Respons: list titik dengan risk score, rationale, dan violation types.
    """
    results = await calculate_placements(placement_type=type, top_n=top_n)
    return {
        "type": type,
        "recommendations": results,
        "total": len(results),
    }
