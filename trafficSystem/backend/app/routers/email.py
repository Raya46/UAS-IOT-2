"""
Email router — sends incident notifications and reports via email.
Uses SMTP with environment variable configuration.
"""
import os
import smtplib
import json
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/email", tags=["email"])


class EmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    incident_id: Optional[str] = None
    attach_report: bool = False


class EmailResponse(BaseModel):
    success: bool
    message: str


def _build_html_body(subject: str, body: str, incident_id: Optional[str] = None) -> str:
    """Build a professional HTML email body."""
    now = datetime.now().strftime("%d %B %Y, %H:%M WIB")
    inc_section = ""
    if incident_id:
        inc_section = f'<div style="margin-top: 16px; padding: 12px; background: #f1f5f9; border-radius: 8px; font-size: 12px; color: #475569;"><strong>Incident ID:</strong> INC-{incident_id[:8].upper()}</div>'

    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; background: #f8fafc; padding: 24px;">
      <div style="background: #1a1a2e; color: white; padding: 20px 24px; border-radius: 12px 12px 0 0;">
        <div style="font-size: 10px; text-transform: uppercase; letter-spacing: 2px; opacity: 0.7; margin-bottom: 4px;">Artery Traffic Intelligence</div>
        <div style="font-size: 18px; font-weight: 700;">{subject}</div>
      </div>
      <div style="background: white; padding: 24px; border: 1px solid #e2e8f0; border-top: none;">
        <div style="font-size: 11px; color: #64748b; margin-bottom: 16px;">{now}</div>
        <div style="font-size: 14px; color: #1e293b; line-height: 1.6; white-space: pre-line;">{body}</div>
        {inc_section}
      </div>
      <div style="padding: 16px 24px; font-size: 10px; color: #94a3b8; text-align: center; border-radius: 0 0 12px 12px; background: #f8fafc;">
        Artery — Intelligent Traffic Management System
      </div>
    </div>
    """


@router.post("/send", response_model=EmailResponse)
async def send_email(req: EmailRequest):
    """Send an email notification."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_from = os.getenv("SMTP_FROM", "") or smtp_user

    if not smtp_user or not smtp_pass:
        raise HTTPException(
            status_code=500,
            detail="SMTP belum dikonfigurasi. Tambahkan SMTP_USER dan SMTP_PASS di .env"
        )

    logger.info(f"[EMAIL] Sending to {req.to} from {smtp_from} via {smtp_host}:{smtp_port}")

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = req.subject
        msg["From"] = smtp_from
        msg["To"] = req.to

        # Plain text fallback
        msg.attach(MIMEText(req.body, "plain", "utf-8"))

        # HTML version
        html = _build_html_body(req.subject, req.body, req.incident_id)
        msg.attach(MIMEText(html, "html", "utf-8"))

        # Attach report PDF if requested
        if req.attach_report and req.incident_id:
            try:
                api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{api_base}/api/reports/incident/{req.incident_id}",
                        timeout=15
                    )
                    if resp.status_code == 200:
                        pdf_part = MIMEApplication(
                            resp.content,
                            Name=f"incident_{req.incident_id[:8]}.pdf"
                        )
                        pdf_part["Content-Disposition"] = (
                            f'attachment; filename="incident_{req.incident_id[:8]}.pdf"'
                        )
                        msg.attach(pdf_part)
            except Exception as e:
                logger.warning(f"[EMAIL] Could not attach report: {e}")

        # Send via SMTP SSL with retry
        last_err = None
        for attempt in range(3):
            try:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                logger.info(f"[EMAIL] Successfully sent to {req.to} (attempt {attempt + 1})")
                return EmailResponse(
                    success=True,
                    message=f"Email berhasil dikirim ke {req.to}"
                )
            except smtplib.SMTPAuthenticationError as e:
                logger.error(f"[EMAIL] Authentication failed: {e}")
                raise HTTPException(
                    status_code=401,
                    detail=f"Gmail authentication gagal. Pastikan App Password benar."
                )
            except Exception as e:
                last_err = e
                logger.warning(f"[EMAIL] Attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    import time
                    time.sleep(1)

        logger.error(f"[EMAIL] All 3 attempts failed: {last_err}")
        raise HTTPException(
            status_code=500,
            detail=f"Gagal mengirim email setelah 3 percobaan: {last_err}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EMAIL] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {e}")
