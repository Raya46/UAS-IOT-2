from fastapi import APIRouter, Response, HTTPException
from datetime import date
from app.services.report_generator import generate_daily_report_pdf, generate_incident_report_pdf

router = APIRouter(prefix="/api/reports", tags=["reports"])

@router.get("/daily/{report_date}")
async def get_daily_report_pdf(report_date: date):
    """Download laporan PDF harian. Format tanggal: YYYY-MM-DD."""
    pdf_bytes = await generate_daily_report_pdf(report_date)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="laporan_{report_date}.pdf"'
        },
    )

@router.get("/incident/{incident_id}")
async def get_incident_report_pdf(incident_id: str):
    """Download laporan PDF detail insiden tunggal. Dibuka di browser tab (inline)."""
    try:
        pdf_bytes = await generate_incident_report_pdf(incident_id)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="laporan_insiden_{incident_id}.pdf"'
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal generate PDF: {str(e)}")
