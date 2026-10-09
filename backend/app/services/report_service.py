"""
MODULE: Automated Report Generation.

Direct response to BOT's recommendation: "automate the system for generating
their reports." Compiles the same real, queried figures already shown on the
Internal Dashboard (KPIs, hazard exposure, combined climate-financial
exposure, recent Risk Advisory Reports) into a single formatted PDF, instead
of an analyst manually copying numbers between screens and a document.

Consistent with this project's honesty rules: every figure in the report
comes directly from analytics_service (the same functions the dashboard
uses) - nothing here is invented or separately computed.
"""
import io
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
)
from sqlalchemy.orm import Session

from app.models.models import RiskAdvisoryNote, User
from app.services import analytics_service
from app.core.export_safety import text_cell
from app.core.timeutil import utcnow

NAVY = colors.HexColor("#12395B")
NAVY_DARK = colors.HexColor("#0A2038")
ACCENT = colors.HexColor("#0FA47F")
LIGHT_GREY = colors.HexColor("#F4F6F8")


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", fontName="Helvetica-Bold", fontSize=20, textColor=NAVY_DARK, spaceAfter=10, leading=24,
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle", fontName="Helvetica", fontSize=10, textColor=colors.grey, spaceAfter=18, leading=13,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading", fontName="Helvetica-Bold", fontSize=13, textColor=NAVY,
        spaceBefore=16, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="BodyNote", fontName="Helvetica-Oblique", fontSize=8.5, textColor=colors.grey, spaceAfter=10,
    ))
    return styles


def _table(headers: list[str], rows: list[list[str]], col_widths=None) -> Table:
    data = [headers] + rows if rows else [headers, ["No data available" for _ in headers]]
    if not rows:
        # merge the "no data" row visually
        data = [headers, ["No data available"] + [""] * (len(headers) - 1)]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _bar_drawing(rows, width_cm: float = 16.5):
    """A small horizontal bar chart (reportlab graphics) for [(label, value, share), ...], at most 6 bars."""
    from reportlab.graphics.shapes import Drawing, Rect, String
    shown = rows[:6]
    row_h, label_w, value_w = 16, 4.2 * cm, 3.4 * cm
    height = max(len(shown), 1) * row_h + 6
    drawing = Drawing(width_cm * cm, height)
    if not shown:
        return drawing
    track_w = width_cm * cm - label_w - value_w
    max_val = max(v for _, v, _ in shown) or 1.0
    for i, (label, value, share) in enumerate(shown):
        y = height - (i + 1) * row_h
        drawing.add(String(0, y + 4, label if len(label) <= 26 else label[:25] + "...", fontSize=8))
        drawing.add(Rect(label_w, y + 2, max(track_w * value / max_val, 1.5), 9, fillColor=colors.HexColor("#C99A2E"), strokeColor=None))
        drawing.add(String(label_w + track_w + 6, y + 4, f"{_compact(value)} ({share}%)", fontSize=8))
    return drawing


def _fmt_tzs(amount: float) -> str:
    return f"{amount:,.0f} TZS"


def _compact(n: float) -> str:
    """55,660,000,000,000 -> '55.66 T' (the dashboard's own compact form)."""
    a = abs(n)
    if a >= 1e12:
        return f"{n / 1e12:.2f} T"
    if a >= 1e9:
        return f"{n / 1e9:.2f} B"
    if a >= 1e6:
        return f"{n / 1e6:.2f} M"
    if a >= 1e3:
        return f"{n / 1e3:.1f} K"
    return f"{n:.0f}"


# The portfolio charts of the dashboard, as tables (title, group_by, metric): the same figures in the same order.
PORTFOLIO_TABLES = [
    ("Loan by borrower type", "borrower_type", "loan"),
    ("Loan by currency", "currency", "loan"),
    ("Loan by sector", "sector", "loan"),
    ("Loan by region", "region", "loan"),
    ("Loan by bank", "institution", "loan"),
    ("Collateral by type", "collateral_type", "collateral"),
    ("Collateral by sector", "collateral_sector", "collateral"),
    ("Collateral by region", "collateral_region", "collateral"),
]


def _portfolio_tables(db: Session, filter_institution_id, filter_region, filter_reporting_period):
    """[(title, [(label, value, share_pct), ...]), ...] for every portfolio chart; 10 groups each."""
    out = []
    for title, group_by, metric in PORTFOLIO_TABLES:
        groups = analytics_service.get_portfolio_breakdown(
            db, group_by=group_by, metric=metric, limit=10, institution_id=None,
            filter_institution_id=filter_institution_id, filter_region=filter_region,
            filter_reporting_period=filter_reporting_period,
        )
        out.append((title, [(g["label"], g["value"], g["share_pct"]) for g in groups]))
    return out


def generate_summary_report_pdf(
    db: Session, generated_by: User, filter_institution_id: str | None = None,
    filter_region: str | None = None, filter_reporting_period: str | None = None,
    validated_only: bool = False,
    filter_hazard_type: str | None = None,
) -> bytes:
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
    )
    story = []

    # ---- Header ----
    story.append(Paragraph("Climate Data Repository", styles["ReportTitle"]))
    story.append(Paragraph("Bank of Tanzania — Automated Analytical Summary Report", styles["ReportSubtitle"]))
    story.append(Paragraph(
        f"Generated by {generated_by.full_name} ({generated_by.role.value}) on "
        f"{utcnow().strftime('%d %B %Y, %H:%M UTC')}",
        styles["BodyNote"],
    ))
    active_filters = [f for f in [
        f"Institution ID: {filter_institution_id}" if filter_institution_id else None,
        f"Region: {filter_region}" if filter_region else None,
        f"Reporting Period: {filter_reporting_period}" if filter_reporting_period else None,
        f"Hazard: {filter_hazard_type} (applies to hazard exposure, combined exposure and map, not to KPI totals)" if filter_hazard_type else None,
        "VALIDATED climate readings only" if validated_only else None,
    ] if f]
    story.append(Paragraph(
        "Filters applied: " + "; ".join(active_filters) if active_filters else "Filters applied: none (sector-wide, all data)",
        styles["BodyNote"],
    ))

    # ---- KPI Summary ----
    kpi = analytics_service.get_kpi_summary(
        db, institution_id=None, filter_institution_id=filter_institution_id,
        filter_region=filter_region, filter_reporting_period=filter_reporting_period,
    )
    story.append(Paragraph("1. Key Performance Indicators (Sector-Wide)", styles["SectionHeading"]))
    story.append(_table(
        ["Metric", "Value"],
        [
            ["Reporting Institutions", str(kpi["total_institutions"])],
            ["Total Submissions", str(kpi["total_submissions"])],
            ["Pending", str(kpi["pending_submissions"])],
            ["Valid", str(kpi["valid_submissions"])],
            ["Invalid", str(kpi["invalid_submissions"])],
            ["Approved", str(kpi["approved_submissions"])],
            ["Rejected", str(kpi["rejected_submissions"])],
            ["Total Borrowers (distinct, active valid records)", str(kpi["total_borrowers"])],
            ["Total Loan Exposure (active, valid records)", _fmt_tzs(kpi["total_loan_exposure_tzs"])],
            ["Total Collateral Value (active, valid records)", _fmt_tzs(kpi["total_collateral_value_tzs"])],
        ],
        col_widths=[10 * cm, 6.5 * cm],
    ))

    # ---- Climate Hazard Exposure ----
    hazard_rows = analytics_service.get_hazard_exposure(
        db, institution_id=None, validated_only=validated_only,
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_reporting_period=filter_reporting_period, filter_hazard_type=filter_hazard_type,
    )
    story.append(Paragraph("2. Climate Hazard Exposure by Region", styles["SectionHeading"]))
    story.append(Paragraph(
        "Loan exposure in regions/periods with each recorded climate hazard "
        "(from real ClimateRecord observations, not institution self-reporting).",
        styles["BodyNote"],
    ))
    story.append(_table(
        ["Region", "Recorded Hazard", "Loan Exposure in Region/Period", "Records"],
        [[h["region"], h["hazard_type"] or "None", _fmt_tzs(h["exposed_loan_amount_tzs"]), str(h["record_count"])]
         for h in hazard_rows],
        col_widths=[4.5 * cm, 3.5 * cm, 5 * cm, 3.5 * cm],
    ))

    # ---- Combined Climate-Financial Exposure ----
    combined_rows = analytics_service.get_combined_climate_financial_exposure(
        db, institution_id=None, validated_only=validated_only,
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_reporting_period=filter_reporting_period, filter_hazard_type=filter_hazard_type,
    )
    story.append(Paragraph("3. Combined Climate-Financial Exposure", styles["SectionHeading"]))
    story.append(Paragraph(
        "Real meteorological readings joined with real loan/collateral exposure for the same "
        "region and reporting period. A blank climate column means no reading exists for that "
        "region/period — it is never estimated.",
        styles["BodyNote"],
    ))
    story.append(_table(
        ["Region", "Period", "Rainfall", "Temp", "Hazards", "Quality", "Loan Exposure"],
        [[
            c["region"], c["reporting_period"],
            f"{c['avg_rainfall_mm']} mm" if c["avg_rainfall_mm"] is not None else "—",
            f"{c['avg_temperature_c']}°C" if c["avg_temperature_c"] is not None else "—",
            ", ".join(c["hazard_types_recorded"]) or "—",
            c["climate_data_quality"] or "—",
            _fmt_tzs(c["total_loan_exposure_tzs"]),
        ] for c in combined_rows],
        col_widths=[2.6 * cm, 2 * cm, 1.9 * cm, 1.7 * cm, 2.8 * cm, 3.2 * cm, 3.3 * cm],
    ))

    # ---- Portfolio breakdown (the dashboard's loan and collateral charts) ----
    story.append(PageBreak())
    story.append(Paragraph("4. Loan Structure and Collateral Exposure", styles["SectionHeading"]))
    story.append(Paragraph(
        "The figures behind the dashboard charts (approved submissions only; ten largest groups, the rest under Others).",
        styles["BodyNote"],
    ))
    for title, rows in _portfolio_tables(db, filter_institution_id, filter_region, filter_reporting_period):
        story.append(Paragraph(title, styles["BodyNote"]))
        story.append(_bar_drawing(rows))
        story.append(_table(
            ["Group", "Amount", "Share"],
            [[label, _fmt_tzs(value), f"{share}%"] for label, value, share in rows] or [["No approved data", "-", "-"]],
            col_widths=[8 * cm, 5.5 * cm, 3 * cm],
        ))
        story.append(Spacer(1, 8))

    # ---- Recent Risk Advisory Reports ----
    story.append(PageBreak())
    notes = db.query(RiskAdvisoryNote).order_by(RiskAdvisoryNote.created_at.desc()).limit(15).all()
    story.append(Paragraph("5. Recent Risk Advisory Reports", styles["SectionHeading"]))
    story.append(Paragraph(
        "Analyst-authored climate risk assessments. Risk levels and recommendations are the "
        "authoring analyst's own professional judgement, not a system-computed score.",
        styles["BodyNote"],
    ))
    note_rows = []
    for n in notes:
        author = db.query(User).filter(User.id == n.created_by_user_id).first()
        note_rows.append([
            n.title,
            n.region or "All regions",
            n.risk_level.value,
            author.full_name if author else "Analyst",
            n.created_at.strftime("%Y-%m-%d"),
        ])
    story.append(_table(
        ["Title", "Region", "Risk Level", "Author", "Date"],
        note_rows,
        col_widths=[5.5 * cm, 3 * cm, 2.5 * cm, 3.5 * cm, 2.5 * cm],
    ))

    story.append(Spacer(1, 24))
    story.append(Paragraph(
        "This report was generated automatically from live system data. It is an internal "
        "supervisory document — figures reflect the CDR prototype's current dataset, which may "
        "include clearly-labelled synthetic climate data where real TMA/PMO data is not yet "
        "available (see docs/ASSUMPTIONS_AND_LIMITATIONS.md).",
        styles["BodyNote"],
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def generate_summary_report_excel(
    db: Session, generated_by: User, filter_institution_id: str | None = None,
    filter_region: str | None = None, filter_reporting_period: str | None = None,
    validated_only: bool = False,
    filter_hazard_type: str | None = None,
) -> bytes:
    """
    Same figures as the PDF report, as a multi-sheet Excel workbook - useful
    when an analyst wants to filter/pivot the numbers themselves rather than
    just read a formatted document.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    def write_sheet(ws, headers, rows):
        for col_idx, h in enumerate(headers, start=1):
            cell = text_cell(ws, 1, col_idx, h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
            ws.column_dimensions[cell.column_letter].width = 20
        for row_idx, row in enumerate(rows, start=2):
            for col_idx, value in enumerate(row, start=1):
                text_cell(ws, row_idx, col_idx, value)

    # ---- KPI Summary ----
    ws1 = wb.active
    ws1.title = "KPI Summary"
    kpi = analytics_service.get_kpi_summary(
        db, institution_id=None, filter_institution_id=filter_institution_id,
        filter_region=filter_region, filter_reporting_period=filter_reporting_period,
    )
    write_sheet(ws1, ["Metric", "Value"], [
        ["Reporting Institutions", kpi["total_institutions"]],
        ["Total Submissions", kpi["total_submissions"]],
        ["Pending", kpi["pending_submissions"]],
        ["Valid", kpi["valid_submissions"]],
        ["Invalid", kpi["invalid_submissions"]],
        ["Approved", kpi["approved_submissions"]],
        ["Rejected", kpi["rejected_submissions"]],
        ["Total Borrowers", kpi["total_borrowers"]],
        ["Total Loan Exposure (TZS)", kpi["total_loan_exposure_tzs"]],
        ["Total Collateral Value (TZS)", kpi["total_collateral_value_tzs"]],
    ])

    # ---- Hazard Exposure ----
    ws2 = wb.create_sheet("Hazard Exposure")
    hazard_rows = analytics_service.get_hazard_exposure(
        db, institution_id=None, validated_only=validated_only,
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_reporting_period=filter_reporting_period, filter_hazard_type=filter_hazard_type,
    )
    write_sheet(ws2, ["Region", "Recorded Hazard", "Loan Exposure in Region/Period (TZS)", "Records"], [
        [h["region"], h["hazard_type"] or "None", h["exposed_loan_amount_tzs"], h["record_count"]]
        for h in hazard_rows
    ])

    # ---- Combined Climate-Financial Exposure ----
    ws3 = wb.create_sheet("Combined Exposure")
    combined_rows = analytics_service.get_combined_climate_financial_exposure(
        db, institution_id=None, validated_only=validated_only,
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_reporting_period=filter_reporting_period, filter_hazard_type=filter_hazard_type,
    )
    write_sheet(ws3, ["Region", "Period", "Avg Rainfall (mm)", "Avg Temp (C)", "Hazards", "Climate Data Quality", "Loan Exposure (TZS)", "Collateral Value (TZS)", "Records"], [
        [
            c["region"], c["reporting_period"],
            c["avg_rainfall_mm"] if c["avg_rainfall_mm"] is not None else None,
            c["avg_temperature_c"] if c["avg_temperature_c"] is not None else None,
            ", ".join(c["hazard_types_recorded"]),
            c["climate_data_quality"] or "",
            c["total_loan_exposure_tzs"], c["total_collateral_value_tzs"], c["record_count"],
        ] for c in combined_rows
    ])

    # ---- Risk Advisory Reports ----
    # ---- Portfolio breakdown ----
    ws_pf = wb.create_sheet("Portfolio Breakdown")
    pf_rows = []
    for title, rows in _portfolio_tables(db, filter_institution_id, filter_region, filter_reporting_period):
        for label, value, share in rows:
            pf_rows.append([title, label, value, share])
    write_sheet(ws_pf, ["Chart", "Group", "Amount (TZS)", "Share (%)"], pf_rows)

    ws4 = wb.create_sheet("Risk Advisory Reports")
    notes = db.query(RiskAdvisoryNote).order_by(RiskAdvisoryNote.created_at.desc()).all()
    note_rows = []
    for n in notes:
        author = db.query(User).filter(User.id == n.created_by_user_id).first()
        note_rows.append([
            n.title, n.region or "All regions", n.hazard_type or "-", n.risk_level.value,
            author.full_name if author else "Analyst", n.narrative, n.recommendation or "",
            n.created_at.strftime("%Y-%m-%d"),
        ])
    write_sheet(ws4, ["Title", "Region", "Hazard", "Risk Level", "Author", "Narrative", "Recommendation", "Date"], note_rows)
    ws4.column_dimensions["F"].width = 50
    ws4.column_dimensions["G"].width = 40

    info_sheet = wb.create_sheet("About This Export", 0)
    info_sheet["A1"] = "Climate Data Repository - Automated Summary Export"
    info_sheet["A2"] = f"Generated by {generated_by.full_name} ({generated_by.role.value}) on {utcnow().strftime('%d %B %Y, %H:%M UTC')}"
    active_filters = [f for f in [
        f"Institution ID: {filter_institution_id}" if filter_institution_id else None,
        f"Region: {filter_region}" if filter_region else None,
        f"Reporting Period: {filter_reporting_period}" if filter_reporting_period else None,
        f"Hazard: {filter_hazard_type} (applies to hazard exposure, combined exposure and map, not to KPI totals)" if filter_hazard_type else None,
        "VALIDATED climate readings only" if validated_only else None,
    ] if f]
    info_sheet["A3"] = "Filters applied: " + ("; ".join(active_filters) if active_filters else "none (sector-wide, all data)")
    info_sheet["A4"] = "Figures may include SYNTHETIC/demo climate data - see docs/ASSUMPTIONS_AND_LIMITATIONS.md"
    info_sheet.column_dimensions["A"].width = 90
    wb.active = 0

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()


# ---------------------------------------------------------------------------
# Image export (Module: dashboard-summary image) - the ICN's own wording
# names "PDF, Excel, CSV and image files" explicitly as the required export
# formats. This renders a single PNG snapshot of the KPI summary and hazard
# exposure - the same real, queried figures as the PDF/Excel reports and the
# dashboard itself, never separately computed or invented.
# ---------------------------------------------------------------------------

_BOT_DARK = (1, 44, 23)
_BOT_GOLD = (187, 123, 2)
_TEXT_DARK = (30, 30, 30)
_TEXT_MUTED = (110, 110, 110)
_BORDER = (225, 222, 214)
_BG = (250, 249, 246)


def _load_font(size: int, bold: bool = False) -> "ImageFont.FreeTypeFont":
    """
    Tries real TTF fonts (installed via the Dockerfile - see its comment)
    first, for legible, professional-looking text; falls back to PIL's tiny
    built-in bitmap font rather than crashing if the container image ever
    lacks them, so image export degrades gracefully instead of failing.
    """
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def generate_summary_report_image(
    db: Session, generated_by: User, filter_institution_id: str | None = None,
    filter_region: str | None = None, filter_reporting_period: str | None = None,
    validated_only: bool = True,
    filter_hazard_type: str | None = None,
) -> bytes:
    kpi = analytics_service.get_kpi_summary(
        db, institution_id=None, filter_institution_id=filter_institution_id,
        filter_region=filter_region, filter_reporting_period=filter_reporting_period,
    )
    hazard_rows = analytics_service.get_hazard_exposure(
        db, institution_id=None, validated_only=validated_only,
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_reporting_period=filter_reporting_period, filter_hazard_type=filter_hazard_type,
    )
    # Collapse to top hazard types by total exposure, for a readable chart.
    by_hazard: dict[str, float] = {}
    for r in hazard_rows:
        by_hazard[r["hazard_type"]] = by_hazard.get(r["hazard_type"], 0.0) + r["exposed_loan_amount_tzs"]
    top_hazards = sorted(by_hazard.items(), key=lambda kv: kv[1], reverse=True)[:8]

    W = 1200
    n_bars = max(len(top_hazards), 1)
    bar_h, bar_gap = 34, 14
    # Height grows with the number of hazard bars actually shown, so a
    # filtered/sparse report never has a large empty gap at the bottom.
    # The dashboard's loan and collateral charts, as small bar panels in two columns (the same figures as the on-screen charts).
    panels = _portfolio_tables(db, filter_institution_id, filter_region, filter_reporting_period)
    panel_rows_shown = 5
    row_h, panel_head_h, panel_pad, panel_gap = 26, 42, 14, 16

    def _panel_h(rows) -> int:
        return panel_head_h + max(min(len(rows), panel_rows_shown), 1) * row_h + panel_pad

    pair_heights = [
        max(_panel_h(panels[i][1]), _panel_h(panels[i + 1][1]) if i + 1 < len(panels) else 0) + panel_gap
        for i in range(0, len(panels), 2)
    ]
    portfolio_h = 50 + sum(pair_heights)
    H = 180 + 36 + 100 + 50 + 30 + 18 + 18 + 12 + n_bars * (bar_h + bar_gap) + portfolio_h + 90
    img = Image.new("RGB", (W, H), _BG)
    draw = ImageDraw.Draw(img)

    f_title = _load_font(30, bold=True)
    f_subtitle = _load_font(16)
    f_small = _load_font(13)
    f_section = _load_font(19, bold=True)
    f_kpi_value = _load_font(26, bold=True)
    f_kpi_label = _load_font(13)
    f_bar_label = _load_font(14)

    # ---- Header band ----
    draw.rectangle([0, 0, W, 130], fill=_BOT_DARK)
    draw.text((40, 24), "Climate Data Repository", font=f_title, fill=(255, 255, 255))
    draw.text((40, 66), "Bank of Tanzania — Dashboard Summary (Image Export)", font=f_subtitle, fill=_BOT_GOLD)
    draw.text((40, 96), f"Generated by {generated_by.full_name} ({generated_by.role.value}) on "
                         f"{utcnow().strftime('%d %B %Y, %H:%M UTC')}", font=f_small, fill=(230, 230, 230))

    active_filters = [f for f in [
        f"Institution ID: {filter_institution_id}" if filter_institution_id else None,
        f"Region: {filter_region}" if filter_region else None,
        f"Reporting Period: {filter_reporting_period}" if filter_reporting_period else None,
        f"Hazard: {filter_hazard_type} (applies to hazard exposure, combined exposure and map, not to KPI totals)" if filter_hazard_type else None,
        "VALIDATED climate readings only" if validated_only else None,
    ] if f]
    filters_text = "Filters applied: " + ("; ".join(active_filters) if active_filters else "none (sector-wide, all data)")
    draw.text((40, 145), filters_text, font=f_small, fill=_TEXT_MUTED)

    # ---- KPI cards ----
    y = 180
    draw.text((40, y), "KPI Summary", font=f_section, fill=_TEXT_DARK)
    y += 36
    cards = [
        ("Total Loan Exposure", f"{kpi['total_loan_exposure_tzs']:,.0f} TZS"),
        ("Total Collateral Value", f"{kpi['total_collateral_value_tzs']:,.0f} TZS"),
        ("Reporting Institutions", str(kpi["total_institutions"])),
        ("Total Submissions", str(kpi["total_submissions"])),
    ]
    card_w, card_h, gap = 270, 100, 20
    for i, (label, value) in enumerate(cards):
        cx = 40 + i * (card_w + gap)
        draw.rounded_rectangle([cx, y, cx + card_w, y + card_h], radius=10, fill=(255, 255, 255), outline=_BORDER, width=1)
        draw.text((cx + 16, y + 16), label, font=f_kpi_label, fill=_TEXT_MUTED)
        draw.text((cx + 16, y + 42), value, font=f_kpi_value, fill=_BOT_DARK)
    y += card_h + 50

    # ---- Hazard exposure bar chart ----
    draw.text((40, y), "Loan Exposure by Recorded Climate Hazard", font=f_section, fill=_TEXT_DARK)
    y += 30
    draw.text((40, y), "Regions/periods where each hazard was the most-frequently recorded observation - a regional", font=f_small, fill=_TEXT_MUTED)
    y += 18
    draw.text((40, y), "pattern, not a claim about any individual loan.", font=f_small, fill=_TEXT_MUTED)
    y += 30

    if top_hazards:
        max_val = max(v for _, v in top_hazards) or 1.0
        bar_area_w = W - 400
        bar_h = 34
        bar_gap = 14
        for hazard, value in top_hazards:
            label = hazard or "None"
            draw.text((40, y + 8), label, font=f_bar_label, fill=_TEXT_DARK)
            bx0 = 200
            bar_len = int((value / max_val) * bar_area_w) if max_val else 0
            draw.rectangle([bx0, y, bx0 + max(bar_len, 2), y + bar_h], fill=_BOT_GOLD)
            draw.text((bx0 + max(bar_len, 2) + 10, y + 8), f"{value:,.0f} TZS", font=f_bar_label, fill=_TEXT_DARK)
            y += bar_h + bar_gap
    else:
        draw.text((40, y), "No data available for the current filters.", font=f_bar_label, fill=_TEXT_MUTED)
        y += 40

    # ---- Loan structure and collateral exposure (the dashboard's portfolio charts) ----
    y += 10
    draw.text((40, y), "Loan Structure & Collateral Exposure", font=f_section, fill=_TEXT_DARK)
    y += 40
    panel_w = (W - 80 - 30) // 2
    for pair_index, start in enumerate(range(0, len(panels), 2)):
        for col in range(2):
            idx = start + col
            if idx >= len(panels):
                break
            title, rows = panels[idx]
            px = 40 + col * (panel_w + 30)
            ph = _panel_h(rows)
            draw.rounded_rectangle([px, y, px + panel_w, y + ph], radius=10, fill=(255, 255, 255), outline=_BORDER, width=1)
            draw.text((px + 16, y + 12), title, font=f_bar_label, fill=_TEXT_DARK)
            shown = rows[:panel_rows_shown]
            if not shown:
                draw.text((px + 16, y + panel_head_h), "No approved data", font=f_small, fill=_TEXT_MUTED)
                continue
            max_val = max(v for _, v, _ in shown) or 1.0
            track_x0, track_w = px + 170, panel_w - 170 - 150
            for r_i, (label, value, share) in enumerate(shown):
                ry = y + panel_head_h + r_i * row_h
                draw.text((px + 16, ry), (label if len(label) <= 18 else label[:17] + "..."), font=f_small, fill=_TEXT_DARK)
                draw.rectangle([track_x0, ry + 3, track_x0 + max(int(track_w * value / max_val), 2), ry + 15], fill=_BOT_GOLD)
                draw.text((track_x0 + track_w + 10, ry), f"{_compact(value)} ({share}%)", font=f_small, fill=_TEXT_DARK)
        y += pair_heights[pair_index]

    # ---- Footer ----
    y = H - 60
    draw.line([(40, y), (W - 40, y)], fill=_BORDER, width=1)
    draw.text((40, y + 14), "Figures may include SYNTHETIC/demo climate data - see docs/ASSUMPTIONS_AND_LIMITATIONS.md", font=f_small, fill=_TEXT_MUTED)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()
