"""
SQLAlchemy ORM model implementing the standard-minimum patient demographic
data model from the spec, including required/optional columns, an enum for
sex, and soft-delete via `deleted_at`.
"""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import Column, String, Date, DateTime, Enum
from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Sex(str, enum.Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    DECLINE = "Decline to Answer"


class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(String(36), primary_key=True, default=_uuid)

    # Required demographics
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    sex = Column(Enum(Sex), nullable=False)
    phone_number = Column(String(10), nullable=False, index=True)
    address_line_1 = Column(String(200), nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(2), nullable=False)
    zip_code = Column(String(10), nullable=False)

    # Optional demographics
    email = Column(String(254), nullable=True)
    address_line_2 = Column(String(200), nullable=True)
    insurance_provider = Column(String(200), nullable=True)
    insurance_member_id = Column(String(50), nullable=True)
    preferred_language = Column(String(50), nullable=False, default="English")
    emergency_contact_name = Column(String(100), nullable=True)
    emergency_contact_phone = Column(String(10), nullable=True)

    # Bookkeeping
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    deleted_at = Column(DateTime, nullable=True)
