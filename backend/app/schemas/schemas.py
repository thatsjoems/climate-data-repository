"""
Pydantic Schemas - validate data going into and coming out of the API.
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
    total_borrowers: int


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


# ---------- INSTITUTION ACCESS REQUESTS ----------
class AccessRequestCreate(BaseModel):
    institution_name: str
    institution_code: Optional[str] = None
    institution_type: InstitutionType = InstitutionType.BANK
    contact_full_name: str
    contact_email: EmailStr
    contact_phone: Optional[str] = None
    message: Optional[str] = None


class AccessRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    institution_name: str
    institution_code: Optional[str] = None
    institution_type: InstitutionType
    contact_full_name: str
    contact_email: str
    contact_phone: Optional[str] = None
    message: Optional[str] = None
    status: str
    review_notes: Optional[str] = None
    created_at: datetime


class AccessRequestDecision(BaseModel):
    notes: Optional[str] = None


class AccessRequestApprovalOut(BaseModel):
    request: AccessRequestOut
    generated_username: str
    generated_temporary_password: str


# ---------- PASSWORD RESET ----------
class PasswordResetRequestCreate(BaseModel):
    username_or_email: str


class PasswordResetRequestOut(BaseModel):
    id: str
    username: str
    full_name: str
    status: str
    review_notes: Optional[str] = None
    created_at: datetime


class PasswordResetApprovalOut(BaseModel):
    request: PasswordResetRequestOut
    new_temporary_password: str


# ---------- NOTIFICATIONS ----------
class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    message: str
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None
    is_read: bool
    created_at: datetime


class UnreadCountOut(BaseModel):
    unread_count: int


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
