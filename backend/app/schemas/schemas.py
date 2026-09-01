"""
Pydantic Schemas - kuthibitisha (validate) data zinazoingia/kutoka kwenye API.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict

from app.models.models import RoleEnum, SubmissionStatus, InstitutionType


# ---------- AUTH ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


# ---------- INSTITUTION ----------
class InstitutionCreate(BaseModel):
    code: str
    name: str
    type: InstitutionType = InstitutionType.BANK
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


class InstitutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    type: InstitutionType
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    is_active: bool
    created_at: datetime


# ---------- USER ----------
class UserCreate(BaseModel):
    full_name: str
    username: str
    email: EmailStr
    password: str
    role: RoleEnum = RoleEnum.INSTITUTION_USER
    institution_id: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    full_name: str
    username: str
    email: str
    role: RoleEnum
    institution_id: Optional[str] = None
    is_active: bool
    created_at: datetime


TokenResponse.model_rebuild()


# ---------- SUBMISSION ----------
class ValidationErrorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    row_number: Optional[int] = None
    column_name: Optional[str] = None
    error_description: str
    severity: str


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    institution_id: str
    submitted_by_user_id: str
    file_name: str
    reporting_period: str
    status: SubmissionStatus
    total_records: int
    valid_records: int
    invalid_records: int
    review_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SubmissionDetailOut(SubmissionOut):
    errors: list[ValidationErrorOut] = []


class ReviewRequest(BaseModel):
    decision: str  # "APPROVE" | "REJECT"
    notes: Optional[str] = None


# ---------- ANALYTICS / DASHBOARD ----------
class KPISummary(BaseModel):
    total_institutions: int
    total_submissions: int
    valid_submissions: int
    invalid_submissions: int
    pending_submissions: int
    approved_submissions: int
    rejected_submissions: int
    total_loan_exposure_tzs: float
    total_collateral_value_tzs: float


class ClimateTrendPoint(BaseModel):
    year: int
    month: Optional[int] = None
    avg_rainfall_mm: Optional[float] = None
    avg_temperature_c: Optional[float] = None


class HazardExposurePoint(BaseModel):
    region: str
    hazard_type: Optional[str] = None
    exposed_loan_amount_tzs: float
    record_count: int


# ---------- AUDIT ----------
class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    details: Optional[str] = None
    created_at: datetime
