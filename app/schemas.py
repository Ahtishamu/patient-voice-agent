"""
Pydantic schemas. This is where server-side validation lives -- the API
never trusts the voice agent (or any client) to have validated data already,
per the spec's "Validate all inputs server-side" requirement.
"""
import re
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict

NAME_RE = re.compile(r"^[A-Za-z'\-]{1,50}$")
PHONE_RE = re.compile(r"^\d{10}$")
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}

VALID_SEX = {"Male", "Female", "Other", "Decline to Answer"}


def _clean_phone(v: str) -> str:
    """Strip formatting characters so '(555) 123-4567' and '5551234567' both work."""
    digits = re.sub(r"\D", "", v or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


class PatientBase(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    address_line_1: str
    city: str
    state: str
    zip_code: str

    email: Optional[EmailStr] = None
    address_line_2: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = "English"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v):
        v = (v or "").strip()
        if not NAME_RE.match(v):
            raise ValueError(
                "must be 1-50 alphabetic characters (hyphens/apostrophes allowed)"
            )
        return v

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v):
        if v > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        if v.year < 1900:
            raise ValueError("date_of_birth is not plausible")
        return v

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, v):
        if v not in VALID_SEX:
            raise ValueError(f"sex must be one of {sorted(VALID_SEX)}")
        return v

    @field_validator("phone_number", "emergency_contact_phone")
    @classmethod
    def validate_phone(cls, v):
        if v is None:
            return v
        digits = _clean_phone(v)
        if not PHONE_RE.match(digits):
            raise ValueError("must be a valid U.S. 10-digit phone number")
        return digits

    @field_validator("state")
    @classmethod
    def validate_state(cls, v):
        v = (v or "").strip().upper()
        if v not in US_STATES:
            raise ValueError("must be a valid 2-letter U.S. state abbreviation")
        return v

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v):
        v = (v or "").strip()
        if not ZIP_RE.match(v):
            raise ValueError("must be a 5-digit or ZIP+4 U.S. zip code")
        return v

    @field_validator("city")
    @classmethod
    def validate_city(cls, v):
        v = (v or "").strip()
        if not (1 <= len(v) <= 100):
            raise ValueError("city must be 1-100 characters")
        return v


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    """All fields optional to support partial updates via PUT."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    phone_number: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    email: Optional[EmailStr] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not NAME_RE.match(v):
            raise ValueError(
                "must be 1-50 alphabetic characters (hyphens/apostrophes allowed)"
            )
        return v

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v):
        if v is None:
            return v
        if v > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        return v

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, v):
        if v is None:
            return v
        if v not in VALID_SEX:
            raise ValueError(f"sex must be one of {sorted(VALID_SEX)}")
        return v

    @field_validator("phone_number", "emergency_contact_phone")
    @classmethod
    def validate_phone(cls, v):
        if v is None:
            return v
        digits = _clean_phone(v)
        if not PHONE_RE.match(digits):
            raise ValueError("must be a valid U.S. 10-digit phone number")
        return digits

    @field_validator("state")
    @classmethod
    def validate_state(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        if v not in US_STATES:
            raise ValueError("must be a valid 2-letter U.S. state abbreviation")
        return v

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v):
        if v is None:
            return v
        if not ZIP_RE.match(v):
            raise ValueError("must be a 5-digit or ZIP+4 U.S. zip code")
        return v


class PatientOut(PatientBase):
    model_config = ConfigDict(from_attributes=True)

    patient_id: str
    created_at: datetime
    updated_at: datetime
