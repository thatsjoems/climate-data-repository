"""
MODULE: Automated Report Generation.

Response to BOT's recommendation to automate report creation. Exclusive to
BOT_USER (Analyst) - consistent with the rest of this project's role
separation, since the report contains climate/submission data.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io
from datetime import datetime

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.models import User, RoleEnum
from app.services.report_service import generate_summary_report_pdf
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
