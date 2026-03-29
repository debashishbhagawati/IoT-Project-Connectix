from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PatientRegisterIn(BaseModel):
    full_name: str = Field(..., min_length=2)
    email: str
    password: str = Field(..., min_length=6)
    age: int | None = Field(default=None, ge=0, le=130)
    gender: str | None = None
    blood_group: str | None = None
    medical_history: str | None = None
    phone: str
    address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None


class DoctorRegisterIn(BaseModel):
    full_name: str = Field(..., min_length=2)
    email: str
    password: str = Field(..., min_length=6)
    qualification: str | None = None
    department: str | None = None
    experience_years: int | None = Field(default=None, ge=0, le=70)
    expertises: str | None = None
    phone: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class DoctorRequestIn(BaseModel):
    doctor_uid: str


class RequestDecisionIn(BaseModel):
    action: Literal["accept", "reject"]


class VitalIngestIn(BaseModel):
    patient_uid: str
    heart_rate: int = Field(..., ge=20, le=250)
    spo2: int = Field(..., ge=50, le=100)
    temperature_c: float = Field(..., ge=30.0, le=45.0)
    systolic_bp: int = Field(..., ge=60, le=250)
    diastolic_bp: int = Field(..., ge=30, le=180)
    respiratory_rate: int = Field(..., ge=4, le=80)
    timestamp: datetime | None = None


class MessageIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=3000)
