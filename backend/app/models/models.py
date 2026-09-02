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
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, Enum as SAEnum
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

    institution = relationship("Institution", back_populates="users")


# ---------------------------------------------------------------------------
# SUBMISSION MANAGEMENT
# ---------------------------------------------------------------------------

class Submission(Base):
    __tablename__ = "submissions"

    id = Column(String, primary_key=True, default=gen_uuid)
    institution_id = Column(String, ForeignKey("institutions.id"), nullable=False)
    submitted_by_user_id = Column(String, ForeignKey("users.id"), nullable=False)

    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    reporting_period = Column(String(20), nullable=False)  # e.g. "2026-Q2"

    status = Column(SAEnum(SubmissionStatus), default=SubmissionStatus.PENDING, nullable=False)

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
    """A single data row (e.g. one loan) extracted from an uploaded Excel submission."""
    __tablename__ = "submission_records"

    id = Column(String, primary_key=True, default=gen_uuid)
    submission_id = Column(String, ForeignKey("submissions.id"), nullable=False)
    row_number = Column(Integer, nullable=False)

    loan_id = Column(String(100), nullable=True)
    borrower_name = Column(String(255), nullable=True)
    loan_amount_tzs = Column(Float, nullable=True)
    collateral_type = Column(String(100), nullable=True)
    collateral_value_tzs = Column(Float, nullable=True)
    region = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    climate_hazard_exposure = Column(String(100), nullable=True)  # e.g. Drought, Flood, None
    is_valid = Column(Boolean, default=True)

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
    Climate / environmental hazard data.
    IMPORTANT: The records loaded via the seed script are SYNTHETIC (sample)
    data used to demonstrate how the analytics will work - NOT real TMA/PMO data.
    """
    __tablename__ = "climate_records"

    id = Column(String, primary_key=True, default=gen_uuid)
    region = Column(String(100), nullable=False)
    district = Column(String(100), nullable=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=True)
    rainfall_mm = Column(Float, nullable=True)
    avg_temperature_c = Column(Float, nullable=True)
    hazard_type = Column(String(100), nullable=True)   # Drought, Flood, Cyclone, None
    hazard_severity = Column(String(20), nullable=True)  # LOW, MEDIUM, HIGH
    source = Column(String(100), default="SYNTHETIC_SAMPLE")


# ---------------------------------------------------------------------------
# AUDIT LOG
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
