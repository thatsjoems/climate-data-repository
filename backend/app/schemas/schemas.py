"""
Pydantic Schemas - validate data going into and coming out of the API.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict

from app.models.models import RoleEnum, SubmissionStatus, InstitutionType, RiskLevel


# ---------- AUTH ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


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


class InstitutionPublicOut(BaseModel):
    """
    Reduced view for INSTITUTION_USER: enough to populate dropdowns and identify
    institutions by name, without exposing other institutions' contact details
    (least-privilege - Module: institution information disclosure).
    """
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    type: InstitutionType
    is_active: bool


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
    must_change_password: bool = False
    created_at: datetime


TokenResponse.model_rebuild()


# ---------- SUBMISSION ----------
class ValidationErrorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    row_number: Optional[int] = None
    column_name: Optional[str] = None
    error_description: str
    severity: str


class SubmissionRecordOut(BaseModel):
    """
    A single submitted row (e.g. one loan), so an institution can review the
    actual data it sent - not just the validation error list.
    """
    model_config = ConfigDict(from_attributes=True)
    row_number: int
    loan_id: Optional[str] = None
    borrower_name: Optional[str] = None
    loan_amount_tzs: Optional[float] = None
    collateral_type: Optional[str] = None
    collateral_value_tzs: Optional[float] = None
    region: Optional[str] = None
    district: Optional[str] = None
    climate_hazard_exposure: Optional[str] = None
    is_valid: bool


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
    records: list[SubmissionRecordOut] = []


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


class CombinedExposurePoint(BaseModel):
    region: str
    reporting_period: str
    avg_rainfall_mm: Optional[float] = None
    avg_temperature_c: Optional[float] = None
    hazard_types_recorded: list[str] = []
    total_loan_exposure_tzs: float
    total_collateral_value_tzs: float
    record_count: int


class RegionMapPoint(BaseModel):
    region: str
    latitude: float
    longitude: float
    total_exposure_tzs: float
    record_count: int
    dominant_hazard: str


# ---------- CLIMATE DATA INGESTION ----------
class ClimateIngestionErrorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    row_number: Optional[int] = None
    column_name: Optional[str] = None
    error_description: str


class ClimateIngestionBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source: str
    dataset_name: Optional[str] = None
    dataset_version: Optional[str] = None
    file_name: Optional[str] = None
    uploaded_by_user_id: Optional[str] = None
    records_received: int
    records_accepted: int
    records_rejected: int
    records_duplicate: int
    status: str
    created_at: datetime


class ClimateIngestionDetailOut(ClimateIngestionBatchOut):
    errors: list[ClimateIngestionErrorOut] = []


class DataQualitySummary(BaseModel):
    total_observations: int
    synthetic_observations: int
    validated_observations: int
    unvalidated_observations: int
    flagged_observations: int
    regions_with_data: int
    regions_missing_data: list[str]
    latest_ingestion_at: Optional[datetime] = None
    total_ingestion_batches: int
    total_records_rejected_all_time: int
    total_records_duplicate_all_time: int


# ---------- RISK ADVISORY REPORTS ----------
class RiskAdvisoryCreate(BaseModel):
    title: str
    region: Optional[str] = None
    hazard_type: Optional[str] = None
    risk_level: RiskLevel
    narrative: str
    recommendation: Optional[str] = None


class RiskAdvisoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    region: Optional[str] = None
    hazard_type: Optional[str] = None
    risk_level: RiskLevel
    narrative: str
    recommendation: Optional[str] = None
    data_snapshot: Optional[str] = None
    created_by_user_id: str
    created_by_name: str = "Analyst"
    created_at: datetime


# ---------- SHARED DECISION SCHEMA (used by Password Reset) ----------
class AccessRequestDecision(BaseModel):
    notes: Optional[str] = None


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
    email_sent: bool = False


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


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    total: int
    limit: int
    offset: int
