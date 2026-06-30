from fastapi import APIRouter
from app.models.schemas import Zone

router = APIRouter(prefix="/api/zones", tags=["zones"])

ZONES: list[Zone] = [
    Zone(
        id="zone-busway-1",
        name="Koridor Transjakarta — Sudirman",
        type="busway_corridor",
        color="#FF6B00",
        coordinates=[
            [106.8200, -6.1800], [106.8210, -6.1800],
            [106.8210, -6.2100], [106.8200, -6.2100],
        ]
    ),
    Zone(
        id="zone-parking-1",
        name="Zona Rawan Parkir Liar — Tanah Abang",
        type="illegal_parking",
        color="#FFD700",
        coordinates=[
            [106.8130, -6.1870], [106.8160, -6.1870],
            [106.8160, -6.1900], [106.8130, -6.1900],
        ]
    ),
]

@router.get("/", response_model=list[Zone])
async def get_zones():
    return ZONES
