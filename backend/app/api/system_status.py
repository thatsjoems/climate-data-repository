"""
MODULE: System status (System Administrator only). The same checks as scripts/system_check.py, for the System Status page.
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_roles
from app.core.timeutil import utcnow
from app.models.models import RoleEnum, User
from app.services.monitoring_service import overall, run_checks

router = APIRouter(prefix="/system", tags=["System status"])


class CheckOut(BaseModel):
    key: str
    title: str
    status: str            # OK, INFO, WARN or CRITICAL
    message: str
    details: dict


class SystemStatusOut(BaseModel):
    generated_at: datetime
    overall: str
    counts: dict
    checks: list[CheckOut]
    monitoring_interval_minutes: int       # 0 = the background monitor (which sends notifications) is off


@router.get("/status", response_model=SystemStatusOut)
def system_status(db: Session = Depends(get_db), current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN))):
    checks = run_checks(db)
    counts = {s: sum(1 for c in checks if c.status == s) for s in ("OK", "INFO", "WARN", "CRITICAL")}
    return SystemStatusOut(
        generated_at=utcnow(), overall=overall(checks), counts=counts,
        checks=[CheckOut(key=c.key, title=c.title, status=c.status, message=c.message, details=c.details) for c in checks],
        monitoring_interval_minutes=settings.MONITOR_INTERVAL_MINUTES,
    )
