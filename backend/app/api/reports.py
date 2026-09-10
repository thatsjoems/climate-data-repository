"""
MODULE: Automated Report Generation.

Response to BOT's recommendation to automate report creation. Exclusive to
BOT_USER (Analyst) - consistent with the rest of this project's role
separation, since the report contains climate/submission data.
"""
import csv
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io
from datetime import datetime

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.models import User, RoleEnum
from app.services.report_service import generate_summary_report_pdf, generate_summary_report_excel
from app.services import analytics_service
from app.services.audit_service import record_audit

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/summary.pdf")
def download_summary_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
):
    """
    Automatically compiles the current KPI summary, climate hazard exposure,
    combined climate-financial exposure, and recent Risk Advisory Reports into
    a single PDF - the same figures already on the dashboard, formatted for
    sharing/filing instead of manual copy-paste into a document.
    """
    pdf_bytes = generate_summary_report_pdf(db, current_user)

    record_audit(
        db, current_user.id, "REPORT_GENERATED", "Report", None,
        "Automated summary report (PDF) generated"
    )

    filename = f"CDR_Summary_Report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/summary.xlsx")
def download_summary_report_excel(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
):
    """
    Same figures as the PDF report (Section 20: Reporting - Excel export),
    as a multi-sheet workbook for analysts who want to filter/pivot the
    numbers themselves rather than read a formatted document.
    """
    excel_bytes = generate_summary_report_excel(db, current_user)

    record_audit(
        db, current_user.id, "REPORT_GENERATED", "Report", None,
        "Automated summary report (Excel) generated"
    )

    filename = f"CDR_Summary_Report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/combined-exposure.csv")
def download_combined_exposure_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
):
    """
    Structured CSV export of Combined Climate-Financial Exposure (Section 20) -
    same underlying data as the dashboard table and the PDF report, in a
    format an analyst can open directly in Excel or feed into another tool.
    A blank climate cell means no reading exists for that region/period -
    the CSV never fills it in.
    """
    rows = analytics_service.get_combined_climate_financial_exposure(db, institution_id=None)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "region", "reporting_period", "avg_rainfall_mm", "avg_temperature_c",
        "hazard_types_recorded", "total_loan_exposure_tzs", "total_collateral_value_tzs", "record_count",
    ])
    for r in rows:
        writer.writerow([
            r["region"], r["reporting_period"],
            r["avg_rainfall_mm"] if r["avg_rainfall_mm"] is not None else "",
            r["avg_temperature_c"] if r["avg_temperature_c"] is not None else "",
            "; ".join(r["hazard_types_recorded"]),
            r["total_loan_exposure_tzs"], r["total_collateral_value_tzs"], r["record_count"],
        ])

    record_audit(db, current_user.id, "REPORT_GENERATED", "Report", None, "Combined exposure CSV export generated")

    filename = f"CDR_Combined_Exposure_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
