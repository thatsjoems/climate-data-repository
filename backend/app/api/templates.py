"""
MODULE D: Standardized Data Template Management.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
import io

from app.core.deps import get_current_user
from app.models.models import User
from app.services.template_generator import generate_loan_collateral_template

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.get("/loan-collateral/download")
def download_loan_collateral_template(current_user: User = Depends(get_current_user)):
    file_bytes = generate_loan_collateral_template()
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=CDR_Loan_Collateral_Template.xlsx"},
    )
