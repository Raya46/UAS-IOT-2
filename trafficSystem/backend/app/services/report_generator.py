import asyncpg
import os
import uuid
from datetime import date, timedelta, datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm

async def generate_daily_report_pdf(report_date: date) -> bytes:
    """Generate laporan PDF harian untuk stakeholder."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        # Ambil statistik hari itu
        stats = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE severity = 'high')    AS high,
                COUNT(*) FILTER (WHERE severity = 'medium')  AS medium,
                COUNT(*) FILTER (WHERE severity = 'low')     AS low,
                COUNT(*) FILTER (WHERE status = 'resolved')  AS resolved,
                AVG(confidence_score) AS avg_confidence
            FROM incidents
            WHERE DATE(occurred_at) = $1
            """,
            report_date,
        )

        by_type = await conn.fetch(
            """
            SELECT type, COUNT(*) as count
            FROM incidents WHERE DATE(occurred_at) = $1
            GROUP BY type ORDER BY count DESC
            """,
            report_date,
        )

        top_hours = await conn.fetch(
            """
            SELECT EXTRACT(HOUR FROM occurred_at)::INTEGER as hour, COUNT(*) as count
            FROM incidents WHERE DATE(occurred_at) = $1
            GROUP BY hour ORDER BY count DESC LIMIT 5
            """,
            report_date,
        )

    finally:
        await conn.close()

    # Buat PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
                             topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle("title", parent=styles["Heading1"],
                                  fontSize=18, spaceAfter=6)
    subtitle_style = ParagraphStyle("subtitle", parent=styles["Normal"],
                                     fontSize=10, textColor=colors.grey, spaceAfter=20)
    section_style = ParagraphStyle("section", parent=styles["Heading2"],
                                    fontSize=13, spaceAfter=8, spaceBefore=14)

    story.append(Paragraph("Laporan Harian Pemantauan Lalu Lintas", title_style))
    story.append(Paragraph(f"Tanggal: {report_date.strftime('%d %B %Y')}", subtitle_style))

    # Ringkasan
    story.append(Paragraph("Ringkasan Eksekutif", section_style))
    summary_data = [
        ["Metrik", "Nilai"],
        ["Total Insiden Terdeteksi", str(stats["total"] or 0)],
        ["Insiden Selesai Ditangani", str(stats["resolved"] or 0)],
        ["Tingkat Penyelesaian", f"{(stats['resolved'] or 0) / max(stats['total'] or 1, 1) * 100:.1f}%"],
        ["Severity Tinggi", str(stats["high"] or 0)],
        ["Severity Sedang", str(stats["medium"] or 0)],
        ["Severity Rendah", str(stats["low"] or 0)],
        ["Rata-rata Confidence Score", f"{(stats['avg_confidence'] or 0) * 100:.1f}%"],
    ]
    summary_table = Table(summary_data, colWidths=[10*cm, 6*cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#333")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f8f8")]),
    ]))
    story.append(summary_table)

    # Distribusi per tipe
    story.append(Paragraph("Distribusi Per Tipe Pelanggaran", section_style))
    type_labels = {
        "illegal_parking": "Parkir Liar",
        "busway_violation": "Pelanggaran Busway",
        "congestion": "Kemacetan",
        "wrong_way": "Lawan Arah",
        "hazard_lights": "Lampu Hazard",
    }
    type_data = [["Tipe Pelanggaran", "Jumlah"]]
    for row in by_type:
        type_data.append([type_labels.get(row["type"], row["type"]), str(row["count"])])

    if len(type_data) > 1:
        type_table = Table(type_data, colWidths=[10*cm, 6*cm])
        type_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FF6B00")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccc")),
        ]))
        story.append(type_table)

    # Jam rawan
    story.append(Paragraph("Jam Rawan (Top 5)", section_style))
    hour_data = [["Jam", "Jumlah Insiden"]]
    for row in top_hours:
        hour_data.append([f"{row['hour']:02d}:00 – {row['hour']:02d}:59", str(row["count"])])

    if len(hour_data) > 1:
        hour_table = Table(hour_data, colWidths=[10*cm, 6*cm])
        hour_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9B59B6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccc")),
        ]))
        story.append(hour_table)

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Dokumen ini digenerate secara otomatis oleh sistem Traffic Intelligence Dashboard.",
        ParagraphStyle("footer", parent=styles["Normal"], fontSize=8, textColor=colors.grey),
    ))

    doc.build(story)
    return buffer.getvalue()


# Helper untuk Bahasa Indonesia
MONTH_NAMES_ID = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
    7: "Jul", 8: "Agu", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"
}

def format_datetime_id(dt: datetime) -> str:
    if not dt:
        return "Belum tersedia"
    day = dt.day
    month = MONTH_NAMES_ID.get(dt.month, str(dt.month))
    year = dt.year
    time_str = dt.strftime("%H:%M:%S")
    return f"{day} {month} {year} {time_str} WIB"

def format_date_id(dt: datetime) -> str:
    if not dt:
        return "Belum tersedia"
    day = dt.day
    month = MONTH_NAMES_ID.get(dt.month, str(dt.month))
    year = dt.year
    return f"{day} {month} {year}"

# Deterministic plate number generator matching frontend algorithm
def get_deterministic_plate_number(uuid_str: str) -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    suffix_letters = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
    hash_val = 0
    for char in uuid_str:
        hash_val = (ord(char) + ((hash_val << 5) - hash_val)) & 0xFFFFFFFF
        if hash_val & 0x80000000:
            hash_val -= 0x100000000
    hash_val = abs(hash_val)
    number = 1000 + (hash_val % 8999)
    char1 = letters[hash_val % 26]
    char2 = suffix_letters[(hash_val >> 2) % 25]
    char3 = suffix_letters[(hash_val >> 4) % 25]
    return f"B {number} {char1}{char2}{char3}"

def get_deterministic_vehicle_info(uuid_str: str, violation_type: str) -> tuple[str, str, str]:
    hash_val = 0
    for char in uuid_str:
        hash_val = (ord(char) + ((hash_val << 5) - hash_val)) & 0xFFFFFFFF
        if hash_val & 0x80000000:
            hash_val -= 0x100000000
    hash_val = abs(hash_val)
    
    if violation_type == "busway_violation":
        models = ["Toyota Avanza", "Suzuki Carry Minibus", "Honda Jazz", "Toyota Kijang Innova"]
        model = models[hash_val % len(models)]
        v_type = "Mobil"
    elif violation_type == "illegal_parking":
        models = ["Toyota Avanza", "Honda HR-V", "Daihatsu Xenia", "Mitsubishi Xpander"]
        model = models[hash_val % len(models)]
        v_type = "Mobil"
    elif violation_type == "wrong_way":
        models = ["Honda Vario 150", "Yamaha NMAX", "Honda Beat", "Yamaha Mio"]
        model = models[hash_val % len(models)]
        v_type = "Sepeda Motor"
    else:
        models = ["Toyota Avanza", "Honda HR-V", "Yamaha NMAX", "Honda Vario"]
        model = models[hash_val % len(models)]
        v_type = "Mobil" if "Avanza" in model or "HR-V" in model else "Sepeda Motor"
        
    return "Benar, Milik Saya", model, v_type

def get_deterministic_owner_name(uuid_str: str) -> str:
    names = [
        "Gilang Bhaskara", "Ahmad Subarjo", "Budi Hermawan", "Dian Sastrowardoyo",
        "Rian Ekky Pradipta", "Joko Widodo", "Prabowo Subianto", "Megawati Soekarnoputri",
        "Anies Baswedan", "Ridwan Kamil", "Sandiaga Uno", "Ganjar Pranowo"
    ]
    hash_val = 0
    for char in uuid_str:
        hash_val = (ord(char) + ((hash_val << 5) - hash_val)) & 0xFFFFFFFF
        if hash_val & 0x80000000:
            hash_val -= 0x100000000
    hash_val = abs(hash_val)
    return names[hash_val % len(names)]

def get_deterministic_address(uuid_str: str) -> str:
    streets = [
        "Jl. Jenderal Sudirman No. 12, Jakarta Pusat",
        "Jl. M.H. Thamrin No. 8, Jakarta Pusat",
        "Jl. Gatot Subroto No. 45, Jakarta Selatan",
        "Jl. HR Rasuna Said Kav. B10, Jakarta Selatan",
        "Jl. Kebon Jeruk Raya No. 14, Jakarta Barat",
        "Jl. Jatinegara Barat No. 89, Jakarta Timur",
        "Jl. Pluit Indah No. 23, Jakarta Utara"
    ]
    hash_val = 0
    for char in uuid_str:
        hash_val = (ord(char) + ((hash_val << 5) - hash_val)) & 0xFFFFFFFF
        if hash_val & 0x80000000:
            hash_val -= 0x100000000
    hash_val = abs(hash_val)
    return streets[hash_val % len(streets)]


async def generate_incident_report_pdf(incident_id: str) -> bytes:
    """Generate laporan PDF detail insiden tunggal (ETLE PMJ untuk pelanggaran individu)."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        row = await conn.fetchrow(
            """
            SELECT i.id, i.type, i.severity, i.confidence_score, i.source_count,
                   i.status, i.assigned_officer, i.assigned_at, i.resolved_at, i.resolution_notes,
                   i.snapshot_url, i.occurred_at, i.updated_at,
                   c.name as camera_name
            FROM incidents i
            LEFT JOIN cameras c ON i.camera_id = c.id
            WHERE i.id = $1::uuid
            """,
            uuid.UUID(incident_id)
        )
        if not row:
            raise ValueError(f"Incident with ID {incident_id} not found")
        incident = dict(row)
    finally:
        await conn.close()

    # Lokasi asset snapshot
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    local_static_dir = os.path.join(root_dir, "frontend", "dist")
    static_dir = os.getenv("STATIC_DIR", local_static_dir)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm,
                             topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    story = []

    # Custom styles
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontSize=18, spaceAfter=4, textColor=colors.HexColor("#1A365D"))
    subtitle_style = ParagraphStyle("subtitle", parent=styles["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=15)
    section_style = ParagraphStyle("section", parent=styles["Heading2"], fontSize=12, spaceAfter=6, spaceBefore=10, textColor=colors.HexColor("#2C5282"))
    normal_style = ParagraphStyle("normal", parent=styles["Normal"], fontSize=9, leading=13, textColor=colors.HexColor("#2D3748"))
    bold_style = ParagraphStyle("bold", parent=styles["Normal"], fontSize=9, fontName="Helvetica-Bold", leading=13, textColor=colors.HexColor("#1A202C"))
    footer_style = ParagraphStyle("footer", parent=styles["Normal"], fontSize=7.5, textColor=colors.grey, alignment=1)

    TYPE_LABELS = {
        "illegal_parking": "Parkir Liar",
        "busway_violation": "Pelanggaran Busway",
        "wrong_way": "Lawan Arah",
        "hazard_lights": "Lampu Hazard",
        "congestion": "Kemacetan"
    }

    violation_label = TYPE_LABELS.get(incident["type"], incident["type"])
    is_individual_violation = incident["type"] != "congestion"

    # 1. Header (Logo & Title)
    logo_file = os.path.join(static_dir, "snapshots", "etle_logo.png")
    if not os.path.exists(logo_file):
        logo_file = os.path.join(root_dir, "frontend", "public", "snapshots", "etle_logo.png")
        
    logo_img = None
    if os.path.exists(logo_file):
        logo_img = Image(logo_file, width=2.2*cm, height=2.2*cm)

    header_text_story = []
    if is_individual_violation:
        header_text_story.append(Paragraph("ETLE PMJ Violation Information", title_style))
        header_text_story.append(Paragraph(f"Dokumen Resmi Penindakan Pelanggaran Lalu Lintas Elektronik — Polda Metro Jaya", subtitle_style))
    else:
        header_text_story.append(Paragraph("Traffic Congestion Incident Information", title_style))
        header_text_story.append(Paragraph(f"Laporan Dokumentasi Penanganan Kemacetan Lalu Lintas — Traffic Intelligence Command", subtitle_style))

    # Header Table
    if logo_img:
        header_table = Table([[logo_img, header_text_story]], colWidths=[2.6*cm, 15.4*cm])
    else:
        header_table = Table([[header_text_story]], colWidths=[18*cm])
    
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4))

    # Helper function to wrap text for tables
    def make_para(text, is_bold=False):
        return Paragraph(text, bold_style if is_bold else normal_style)

    if is_individual_violation:
        # --- FORMAT A: PELANGGARAN INDIVIDU (EMAIL ETLE STYLE) ---
        plate_num = get_deterministic_plate_number(incident_id)
        veh_status, veh_model, veh_type = get_deterministic_vehicle_info(incident_id, incident["type"])
        owner_name = get_deterministic_owner_name(incident_id)
        address = get_deterministic_address(incident_id)
        occurred_at_str = format_datetime_id(incident["occurred_at"])
        limit_date_str = format_date_id(incident["occurred_at"] + timedelta(days=7))

        # Salam Keselamatan Banner
        salam_data = [[
            Paragraph(
                "<b>Salam Keselamatan,</b><br/><br/>"
                "Selamat! Konfirmasi telah berhasil dilakukan.<br/>"
                "Dalam waktu paling lama 2x24 jam, kami akan mengirimkan kode BRIVA untuk menyelesaikan pelanggaran Anda.<br/>"
                "Terima kasih atas kesediaan Anda menyelesaikan pelanggaran ini secara kooperatif.",
                ParagraphStyle("salam", parent=styles["Normal"], fontSize=9.5, leading=14, textColor=colors.HexColor("#1A365D"))
            )
        ]]
        salam_table = Table(salam_data, colWidths=[18*cm])
        salam_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EBF8FF")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#BEE3F8")),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ]))
        story.append(salam_table)
        story.append(Spacer(1, 12))

        # Status History Builder
        status_history = []
        status_history.append(f"NEW ({format_date_id(incident['occurred_at'])})")
        status_history.append(f"TERKIRIM ({format_date_id(incident['occurred_at'])})")
        if incident["assigned_at"]:
            status_history.append(f"TERKONFIRMASI ({format_date_id(incident['assigned_at'])})")
        else:
            status_history.append(f"TERKONFIRMASI ({format_date_id(incident['occurred_at'])})")
        if incident["resolved_at"]:
            status_history.append(f"SELESAI ({format_date_id(incident['resolved_at'])})")
        else:
            status_history.append(f"SELESAI ({format_date_id(incident['updated_at'])})")
        
        status_history_str = "<br/>".join(status_history)

        # Info Grid (No Pol, Pada, Lokasi, Tipe, Status, BRIVA, Ref, Batas)
        info_data = [
            [make_para("<b>No Pol:</b>"), make_para(plate_num, True), make_para("<b>Status:</b>"), Paragraph(status_history_str, normal_style)],
            [make_para("<b>Pada:</b>"), make_para(occurred_at_str), make_para("<b>Kode BRIVA:</b>"), make_para(f"BRIVA-8899{incident_id[:8].upper()}", True)],
            [make_para("<b>Lokasi:</b>"), make_para(incident["camera_name"] or "Lajur Jalan"), make_para("<b>Ref Pembayaran:</b>"), make_para(f"REF-{incident_id[-8:].upper()}", True)],
            [make_para("<b>Tipe:</b>"), make_para(violation_label), make_para("<b>Batas Konfirmasi:</b>"), make_para(limit_date_str)]
        ]
        info_table = Table(info_data, colWidths=[2.5*cm, 6.5*cm, 3.5*cm, 5.5*cm])
        info_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 15))

        # DATA KONFIRMASI Section Title
        banner_data = [[Paragraph("<font color='white'><b>DATA KONFIRMASI</b></font>", ParagraphStyle("banner_text", parent=styles["Normal"], alignment=1, fontSize=11, fontName="Helvetica-Bold"))]]
        banner_table = Table(banner_data, colWidths=[18*cm])
        banner_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1A365D")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(banner_table)
        story.append(Spacer(1, 8))

        # Vehicle & Violator Side-by-Side
        veh_data = [
            [Paragraph("<b>KENDARAAN</b>", ParagraphStyle("sub_hdr", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#2C5282"), spaceAfter=4))],
            [make_para(f"<b>Status:</b> {veh_status}")],
            [make_para(f"<b>Merk/Model:</b> {veh_model}")],
            [make_para(f"<b>TIPE:</b> {veh_type}")]
        ]
        veh_table = Table(veh_data, colWidths=[8.5*cm])
        veh_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        violator_data = [
            [Paragraph("<b>PELANGGAR</b>", ParagraphStyle("sub_hdr", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#2C5282"), spaceAfter=4))],
            [make_para("<b>Pengendara:</b> Betul Saya Pengendaranya")],
            [make_para(f"<b>Nama:</b> {owner_name}")],
            [make_para(f"<b>Alamat:</b> {address}")]
        ]
        violator_table = Table(violator_data, colWidths=[8.5*cm])
        violator_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        columns_table = Table([[veh_table, violator_table]], colWidths=[9*cm, 9*cm])
        columns_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(columns_table)
        story.append(Spacer(1, 15))
        
        story.append(Paragraph("BUKTI FOTO DETEKSI AI", section_style))

    else:
        # --- FORMAT B: KEMACETAN LALU LINTAS ---
        occurred_at_str = format_datetime_id(incident["occurred_at"])
        resolved_at_str = format_datetime_id(incident["resolved_at"] or incident["updated_at"])
        officer = incident["assigned_officer"] or "Dishub Patroli"
        res_notes = incident["resolution_notes"] or "Arus lalu lintas kembali lancar setelah pengaturan manual."

        # Ringkasan Penanganan Banner
        salam_data = [[
            Paragraph(
                "<b>Salam Keselamatan,</b><br/><br/>"
                "Laporan penanganan kemacetan telah diselesaikan secara prosedural di lapangan oleh tim patroli dinas perhubungan.<br/>"
                "Berikut adalah detail data kejadian kemacetan yang telah dicatat oleh sistem pemantauan lalu lintas.",
                ParagraphStyle("salam_c", parent=styles["Normal"], fontSize=9.5, leading=14, textColor=colors.HexColor("#2C5282"))
            )
        ]]
        salam_table = Table(salam_data, colWidths=[18*cm])
        salam_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ]))
        story.append(salam_table)
        story.append(Spacer(1, 12))

        # Info Grid
        info_data = [
            [make_para("<b>ID Insiden:</b>"), make_para(f"INC-{incident_id[:8].upper()}", True), make_para("<b>Severity:</b>"), make_para(incident["severity"].upper(), True)],
            [make_para("<b>Waktu Mulai:</b>"), make_para(occurred_at_str), make_para("<b>Jumlah Sinyal:</b>"), make_para(f"{incident['source_count']} Sinyal")],
            [make_para("<b>Lokasi Jalan:</b>"), make_para(incident["camera_name"] or "Lajur Jalan"), make_para("<b>Petugas Lapangan:</b>"), make_para(officer, True)],
            [make_para("<b>Waktu Selesai:</b>"), make_para(resolved_at_str), make_para("<b>Akurasi AI:</b>"), make_para(f"{int(incident['confidence_score']*100)}%")]
        ]
        info_table = Table(info_data, colWidths=[3*cm, 6*cm, 3.5*cm, 5.5*cm])
        info_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 15))

        # DATA PENANGANAN & RESOLUSI
        banner_data = [[Paragraph("<font color='white'><b>DATA PENANGANAN & RESOLUSI KASUS</b></font>", ParagraphStyle("banner_text", parent=styles["Normal"], alignment=1, fontSize=11, fontName="Helvetica-Bold"))]]
        banner_table = Table(banner_data, colWidths=[18*cm])
        banner_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#2C5282")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(banner_table)
        story.append(Spacer(1, 8))

        # Calculate duration dynamically
        duration_min = 42
        if incident["resolved_at"] and incident["occurred_at"]:
            diff = incident["resolved_at"] - incident["occurred_at"]
            duration_min = max(int(diff.total_seconds() / 60), 1)

        # Disposition Details
        disposition_data = [
            [make_para("<b>Total Durasi Penanganan:</b>"), make_para(f"{duration_min} Menit", True)],
            [make_para("<b>Status Pemulihan Lajur:</b>"), make_para("100% Arus Mengalir Lancar", True)],
            [make_para("<b>Catatan Resolusi Akhir:</b>"), Paragraph(res_notes, normal_style)]
        ]
        disposition_table = Table(disposition_data, colWidths=[5*cm, 13*cm])
        disposition_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#EDF2F7")),
        ]))
        story.append(disposition_table)
        story.append(Spacer(1, 15))

        story.append(Paragraph("BUKTI FOTO LOKASI TERAKHIR", section_style))

    # 4. Bukti Foto Snapshot
    snapshot_file = None
    if incident["snapshot_url"]:
        filename = os.path.basename(incident["snapshot_url"])
        snapshot_file = os.path.join(static_dir, "snapshots", filename)
        if not os.path.exists(snapshot_file):
            snapshot_file = os.path.join(root_dir, "frontend", "public", "snapshots", filename)
            
    if not snapshot_file or not os.path.exists(snapshot_file):
        # Fallback to type-specific image or default
        fallback_name = f"{incident['type']}.png"
        snapshot_file = os.path.join(static_dir, "snapshots", fallback_name)
        if not os.path.exists(snapshot_file):
            snapshot_file = os.path.join(root_dir, "frontend", "public", "snapshots", fallback_name)
        if not os.path.exists(snapshot_file):
            snapshot_file = os.path.join(static_dir, "snapshots", "default.png")

    if os.path.exists(snapshot_file):
        snap_img = Image(snapshot_file, width=12*cm, height=9*cm)
        snap_img.hAlign = 'CENTER'
        story.append(snap_img)
    else:
        story.append(Paragraph("[Gambar bukti deteksi tidak tersedia]", ParagraphStyle("missing_img", parent=styles["Normal"], textColor=colors.red, alignment=1)))

    # 5. Footer & Legal Notice
    story.append(Spacer(1, 25))
    notice_text = (
        "Dokumen ini diterbitkan oleh Polda Metro Jaya / Dinas Perhubungan Provinsi DKI Jakarta sebagai bukti penindakan hukum "
        "yang sah secara elektronik (E-TLE) berdasarkan rekaman sensor AI Traffic Command. Kode BRIVA di atas merupakan "
        "identifikasi billing resmi untuk penyelesaian pelanggaran denda administrasi yudisial."
        if is_individual_violation else
        "Laporan ini merupakan arsip resmi penanganan insiden kemacetan jalan raya DKI Jakarta yang diverifikasi secara "
        "otomatis oleh Traffic Intelligence Command Center."
    )
    story.append(Paragraph(notice_text, footer_style))

    doc.build(story)
    return buffer.getvalue()
