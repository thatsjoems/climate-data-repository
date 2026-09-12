"""
Database Models - SQLAlchemy ORM.

Tables present:
- User, Institution               -> Identity & Access
- Submission, SubmissionRecord, ValidationError -> Submission Management
- ClimateRecord                    -> Climate/weather data (SAMPLE/SYNTHETIC data - see README)
- AuditLog                         -> Tracking of important system events
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Date, ForeignKey, Text, Enum as SAEnum
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# ENUMS
# ---------------------------------------------------------------------------

class RoleEnum(str, enum.Enum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"          # Overall system administrator (BOT IT)
    BOT_USER = "BOT_USER"                  # Internal Bank of Tanzania user (review/analysis)
    INSTITUTION_USER = "INSTITUTION_USER"  # External reporting institution user (bank, TMA, etc.)


class SubmissionStatus(str, enum.Enum):
    PENDING = "PENDING"                # Received, not yet validated
    VALID = "VALID"                    # Validation passed with no errors
    INVALID = "INVALID"                # Validation found errors - awaiting correction
    APPROVED = "APPROVED"              # Reviewed and approved by a BOT_USER
    REJECTED = "REJECTED"              # Reviewed and rejected by a BOT_USER
    SUPERSEDED = "SUPERSEDED"          # Replaced by a newer submission for the same
                                        # institution + reporting_period; excluded from analytics


class InstitutionType(str, enum.Enum):
    BANK = "BANK"
    METEOROLOGICAL_AUTHORITY = "METEOROLOGICAL_AUTHORITY"
    GOVERNMENT_AGENCY = "GOVERNMENT_AGENCY"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# IDENTITY & ACCESS
# ---------------------------------------------------------------------------

class Institution(Base):
    __tablename__ = "institutions"

    id = Column(String, primary_key=True, default=gen_uuid)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    type = Column(SAEnum(InstitutionType), default=InstitutionType.BANK, nullable=False)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="institution")
    submissions = relationship("Submission", back_populates="institution")


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    full_name = Column(String(255), nullable=False)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.INSTITUTION_USER)
    institution_id = Column(String, ForeignKey("institutions.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    # Auth hardening (Module A / Solution 2 - "secure user authentication"):
    # brute-force lockout tracking and a flag forcing a password change the next
    # time someone logs in with a temporary/admin-issued password.
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    must_change_password = Column(Boolean, default=False, nullable=False)

    institution = relationship("Institution", back_populates="users")


# ---------------------------------------------------------------------------
# REFRESH TOKENS (Module: session security)
# ---------------------------------------------------------------------------

class RefreshToken(Base):
    """
    A long-lived, revocable credential used only to obtain new short-lived
    access tokens - never used to authorize an API request directly. Storing
    it here (hashed, never the raw token) is what makes server-side
    revocation possible: a stateless JWT alone cannot be invalidated before
    its own expiry, but a DB row can be marked revoked at any time (logout,
    admin-forced deactivation, suspected compromise).

    Rotated on every use (Module: token rotation) - each refresh consumes
    this row (revoked_at set) and issues a brand new one. If a refresh token
    is ever reused after rotation, that is a strong signal of theft/replay.
    """
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)  # SHA-256 hex digest
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# SUBMISSION MANAGEMENT
# ---------------------------------------------------------------------------

class Submission(Base):
    __tablename__ = "submissions"

    id = Column(String, primary_key=True, default=gen_uuid)
    institution_id = Column(String, ForeignKey("institutions.id"), nullable=False, index=True)
    submitted_by_user_id = Column(String, ForeignKey("users.id"), nullable=False)

    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    reporting_period = Column(String(20), nullable=False, index=True)  # e.g. "2026-Q2"

    status = Column(SAEnum(SubmissionStatus), default=SubmissionStatus.PENDING, nullable=False, index=True)

    total_records = Column(Integer, default=0)
    valid_records = Column(Integer, default=0)
    invalid_records = Column(Integer, default=0)

    reviewed_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    review_notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    institution = relationship("Institution", back_populates="submissions")
    records = relationship("SubmissionRecord", back_populates="submission", cascade="all, delete-orphan")
    errors = relationship("ValidationError", back_populates="submission", cascade="all, delete-orphan")


class SubmissionRecord(Base):
    """
    A single data row (one loan) extracted from an uploaded Excel submission.

    Field structure mirrors BOT's own official "Climate Data Template" exactly
    (38 columns) - not a simplified prototype subset. Column groups, matching
    the template's own layout:
      A. Borrower/Branch info   B. Loan details
      C. Location of invested loan (region/district/ward/village + GPS)
      D. Collateral details + its own location (region/district/ward/village + GPS)
      E. Climate-risk insurance on the collateral
    """
    __tablename__ = "submission_records"

    id = Column(String, primary_key=True, default=gen_uuid)
    submission_id = Column(String, ForeignKey("submissions.id"), nullable=False)
    row_number = Column(Integer, nullable=False)
    is_valid = Column(Boolean, default=True)

    # ---- A. Borrower / Branch info ----
    customer_id = Column(String(100), nullable=True, index=True)  # BOT's own real identifier - not a name
    branch_code = Column(String(50), nullable=True)
    branch_name = Column(String(255), nullable=True)
    client_type = Column(String(50), nullable=True)          # Corporations, Individuals, Non-salaried, Staff
    business_size = Column(String(50), nullable=True)        # Large, Medium, Micro, Small
    annual_turnover_tzs = Column(Float, nullable=True)

    # ---- B. Loan details ----
    loan_id = Column(String(100), nullable=True, index=True)  # "Loan number" in the official template
    disbursement_date = Column(String(30), nullable=True)     # kept as text - BOT's own sample data is not ISO-clean
    maturity_date = Column(String(30), nullable=True)
    currency = Column(String(10), nullable=True)              # TZS, USD, Other
    loan_amount_tzs = Column(Float, nullable=True)             # "TZS Disbursed Amount"
    outstanding_principal_tzs = Column(Float, nullable=True)
    annual_interest_rate = Column(Float, nullable=True)
    loan_type = Column(String(50), nullable=True)              # Business, Mortgage, Personal
    loan_economic_activity = Column(String(100), nullable=True)
    loan_purpose = Column(String(255), nullable=True)
    asset_classification = Column(String(50), nullable=True)   # Current, Doubtful, Sub-standard

    # ---- C. Location of invested loan ----
    region = Column(String(100), nullable=True, index=True)    # kept name "region" - the loan's own location, used throughout existing analytics
    district = Column(String(100), nullable=True)
    ward = Column(String(150), nullable=True)
    village = Column(String(150), nullable=True)               # "Street/village"
    loan_latitude = Column(Float, nullable=True)
    loan_longitude = Column(Float, nullable=True)

    # ---- D. Collateral details + its own location ----
    collateral_type = Column(String(150), nullable=True)        # "Collateral Pledged" - 21 official categories
    collateral_pledged_date = Column(String(30), nullable=True)
    collateral_value_tzs = Column(Float, nullable=True)         # "TZS Market value of the collateral"
    collateral_forced_sale_value_tzs = Column(Float, nullable=True)
    collateral_economic_activity = Column(String(100), nullable=True)
    collateral_region = Column(String(100), nullable=True)
    collateral_district = Column(String(100), nullable=True)
    collateral_ward = Column(String(150), nullable=True)
    collateral_village = Column(String(150), nullable=True)
    collateral_latitude = Column(Float, nullable=True)
    collateral_longitude = Column(Float, nullable=True)

    # ---- E. Climate-risk insurance on the collateral ----
    insurance_coverage = Column(String(10), nullable=True)      # YES / NO
    insurance_policy_type = Column(String(150), nullable=True)
    insurance_provider_name = Column(String(255), nullable=True)
    insurance_value_protected_tzs = Column(Float, nullable=True)

    # Legacy field - the official template has no borrower-name field (only
    # customer_id), so this is never populated by new uploads. Kept nullable
    # so any pre-existing rows/reports referencing it don't break.
    borrower_name = Column(String(255), nullable=True)
    climate_hazard_exposure = Column(String(100), nullable=True)  # e.g. Drought, Flood, None

    submission = relationship("Submission", back_populates="records")


class ValidationError(Base):
    __tablename__ = "validation_errors"

    id = Column(String, primary_key=True, default=gen_uuid)
    submission_id = Column(String, ForeignKey("submissions.id"), nullable=False)
    row_number = Column(Integer, nullable=True)
    column_name = Column(String(100), nullable=True)
    error_description = Column(String(500), nullable=False)
    severity = Column(String(20), default="ERROR")  # ERROR | WARNING

    submission = relationship("Submission", back_populates="errors")


# ---------------------------------------------------------------------------
# CLIMATE DATA (SAMPLE / SYNTHETIC - see README for details)
# ---------------------------------------------------------------------------

class ClimateRecord(Base):
    """
    Climate / environmental observation record.

    IMPORTANT: Records loaded via the seed script are SYNTHETIC (sample) data
    used to demonstrate how the analytics will work - NOT real TMA/PMO data.
    `source` and `quality_flag` make this explicit on every row so it can
    never be silently displayed as authoritative.

    Extended with provenance/quality-control fields (Module: Climate Data
    Model Improvement) so the same table can later receive real TMA
    observations through an ingestion adapter without a schema redesign.
    Units are fixed for this system: rainfall in millimetres (mm),
    temperature in degrees Celsius (°C) - not stored per-row since they never
    vary here.

    Backward compatible: every new field is nullable, so existing rows and
    existing code that only sets the original fields keep working unchanged.
    """
    __tablename__ = "climate_records"

    id = Column(String, primary_key=True, default=gen_uuid)

    # ---- Core observation (original fields - unchanged) ----
    region = Column(String(100), nullable=False, index=True)
    district = Column(String(100), nullable=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=True)
    rainfall_mm = Column(Float, nullable=True)
    avg_temperature_c = Column(Float, nullable=True)
    hazard_type = Column(String(100), nullable=True)   # Drought, Flood, Cyclone, None
    hazard_severity = Column(String(20), nullable=True)  # LOW, MEDIUM, HIGH
    source = Column(String(100), default="SYNTHETIC_SAMPLE", index=True)

    # ---- Additional observation detail ----
    temperature_min_c = Column(Float, nullable=True)
    temperature_max_c = Column(Float, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    observation_date = Column(Date, nullable=True, index=True)  # exact date, when known at daily granularity

    # ---- Temporal integration (explicit, not silently assumed) ----
    reporting_period = Column(String(20), nullable=True, index=True)   # e.g. "2026-Q3" - aligns with financial reporting_period
    period_type = Column(String(20), nullable=True)        # DAILY, MONTHLY, QUARTERLY, ANNUAL

    # ---- Provenance / traceability ----
    dataset_name = Column(String(255), nullable=True)
    dataset_version = Column(String(50), nullable=True)
    station_id = Column(String(100), nullable=True, index=True)
    station_name = Column(String(255), nullable=True)
    source_record_id = Column(String(255), nullable=True)  # source system's own ID, for dedup on re-ingestion
    source_reference = Column(Text, nullable=True)         # citation/URL/document this came from

    # ---- Quality control / ingestion metadata ----
    quality_flag = Column(String(30), default="UNVALIDATED")  # UNVALIDATED, VALIDATED, FLAGGED, SYNTHETIC
    processing_method = Column(String(100), nullable=True)    # e.g. SYNTHETIC_SEED, TMA_INGESTION, MANUAL_ENTRY
    ingestion_timestamp = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# RISK ADVISORY REPORTS (Climate Risk Assessment & Supervisory Reporting)
# ---------------------------------------------------------------------------

class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskAdvisoryNote(Base):
    """
    An analyst-authored climate risk advisory note - the direct implementation of the
    ICN's core objective to 'strengthen climate risk assessment' and support
    'supervisory activities and evidence-based decision-making'.

    IMPORTANT (by design, per project honesty rules): the risk_level and narrative
    are the BOT Analyst's own professional judgement, not a system-computed score.
    The system only supplies the underlying data_snapshot (real aggregated figures
    at the time of writing) so the note is defensible and auditable - it never
    invents or infers a risk rating on the analyst's behalf.

    Notes are append-only (no edit/delete) so they function as a defensible,
    timestamped supervisory record - consistent with the audit log.
    """
    __tablename__ = "risk_advisory_notes"

    id = Column(String, primary_key=True, default=gen_uuid)
    title = Column(String(255), nullable=False)
    region = Column(String(100), nullable=True)          # null = applies broadly / multiple regions
    hazard_type = Column(String(100), nullable=True)      # null = general / cross-hazard note
    risk_level = Column(SAEnum(RiskLevel), nullable=False)

    narrative = Column(Text, nullable=False)               # analyst's assessment in their own words
    recommendation = Column(Text, nullable=True)            # analyst's recommendation to BOT decision-makers

    data_snapshot = Column(Text, nullable=True)             # JSON string: real figures the note was based on

    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# SHARED STATUS ENUM (used by Password Reset Requests below)
# ---------------------------------------------------------------------------

class AccessRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# ---------------------------------------------------------------------------
# PASSWORD RESET REQUESTS
# ---------------------------------------------------------------------------

class PasswordResetRequest(Base):
    """
    A user-initiated request to reset their password. Mirrors the same
    'request -> admin review -> credential handed over out-of-band' pattern
    used for institution access requests, since no SMTP integration is
    available to email a reset link automatically.
    """
    __tablename__ = "password_reset_requests"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    status = Column(SAEnum(AccessRequestStatus), default=AccessRequestStatus.PENDING, nullable=False)
    reviewed_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    review_notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# NOTIFICATIONS
# ---------------------------------------------------------------------------

class Notification(Base):
    """
    In-app notification for a single user (e.g. 'your submission was approved',
    'a new submission is awaiting review'). Polled by the frontend bell icon.
    """
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False, default="INFO")  # e.g. SUBMISSION_UPLOADED, SUBMISSION_REVIEWED
    message = Column(String(500), nullable=False)
    related_entity_type = Column(String(100), nullable=True)   # e.g. "Submission"
    related_entity_id = Column(String, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# AUDIT LOG
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# CLIMATE DATA INGESTION (Module: TMA ingestion adapter/pipeline)
# ---------------------------------------------------------------------------

class ClimateIngestionBatch(Base):
    """
    Records one ingestion run (whether the current file-upload adapter, or a
    future TMA API/CSV/SFTP feed) so an analyst can always answer: where did
    this data come from, when, and what happened to it. This is the
    provenance/audit trail for climate data specifically, distinct from the
    general AuditLog (which logs the ingestion *event* but not per-row detail).
    """
    __tablename__ = "climate_ingestion_batches"

    id = Column(String, primary_key=True, default=gen_uuid)
    source = Column(String(100), nullable=False)          # e.g. "MANUAL_UPLOAD", "TMA_FILE" - never invented as "TMA_API" unless real
    dataset_name = Column(String(255), nullable=True)
    dataset_version = Column(String(50), nullable=True)
    file_name = Column(String(500), nullable=True)
    uploaded_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)

    records_received = Column(Integer, default=0, nullable=False)
    records_accepted = Column(Integer, default=0, nullable=False)
    records_rejected = Column(Integer, default=0, nullable=False)
    records_duplicate = Column(Integer, default=0, nullable=False)

    status = Column(String(30), default="COMPLETED", nullable=False)  # COMPLETED, FAILED
    error_summary = Column(Text, nullable=True)  # human-readable summary of rejected-row reasons (not every row - see ClimateIngestionError for that)

    created_at = Column(DateTime, default=datetime.utcnow)


class ClimateIngestionError(Base):
    """One rejected row from a ClimateIngestionBatch, with the specific reason - so a rejected observation is traceable, not just a count."""
    __tablename__ = "climate_ingestion_errors"

    id = Column(String, primary_key=True, default=gen_uuid)
    batch_id = Column(String, ForeignKey("climate_ingestion_batches.id"), nullable=False)
    row_number = Column(Integer, nullable=True)
    column_name = Column(String(100), nullable=True)
    error_description = Column(Text, nullable=False)


# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)      # e.g. LOGIN, SUBMISSION_CREATED, USER_CREATED
    entity_type = Column(String(100), nullable=True)  # e.g. Submission, User
    entity_id = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
