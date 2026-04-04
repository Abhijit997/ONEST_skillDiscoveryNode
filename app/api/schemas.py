"""
Pydantic request / response schemas for the worker_stage API.
"""

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ── Re-export enum values so the API docs show allowed values ──


SKILL_CATEGORIES = [
    "plumbing", "electrical", "carpentry", "welding", "masonry",
    "painting", "hvac", "tailoring", "driving", "cooking",
    "housekeeping", "gardening", "security", "delivery",
    "construction", "mechanic", "beauty", "other",
]

SOURCE_CHANNELS = ["csv", "telegram", "chat_simulator", "api", "manual"]

AVAILABILITY_STATUSES = ["available", "unavailable", "partially_available"]

PREFERRED_SHIFTS = ["morning", "afternoon", "evening", "night", "flexible"]

WORKER_STATUSES = [
    "active", "old_duplicate", "pending_verification",
    "verified", "rejected", "inactive",
]

FULFILLMENT_TYPES = ["REMOTE", "HYBRID", "ONSITE"]


# ── Request schemas ───────────────────────────


class WorkerStageCreate(BaseModel):
    """Payload for inserting a new worker_stage record."""

    name: str = Field(..., min_length=1, max_length=255, examples=["Ramesh Kumar"])
    dob: Optional[date] = Field(None, description="Date of birth (YYYY-MM-DD)", examples=["1990-01-15"])
    gender: Optional[str] = Field(None, max_length=20, examples=["Male"])
    aadhar_hash: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[a-fA-F0-9]{64}$",
        description="SHA-256 hex digest of the Aadhaar number. Never send the raw Aadhaar.",
        examples=["e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"],
    )

    # Location
    district: str = Field(..., max_length=255, examples=["Bengaluru Urban"])
    taluk: Optional[str] = Field(None, max_length=255, examples=["Anekal"])
    city_village: Optional[str] = Field(None, max_length=255, examples=["Chandapura"])
    state_name: Optional[str] = Field(None, max_length=255, examples=["Karnataka"])
    state_code: Optional[str] = Field(None, max_length=10, description="ISO state code", examples=["KA"])
    city_code: Optional[str] = Field(None, max_length=20, description="STD telephone code", examples=["std:080"])
    area_code: str = Field(..., max_length=10, description="PIN/ZIP code (mandatory)", examples=["560001"])
    door: Optional[str] = Field(None, max_length=100, description="Door / flat number", examples=["#42"])
    building: Optional[str] = Field(None, max_length=255, description="Building / apartment name", examples=["Sunrise Apartments"])
    street: Optional[str] = Field(None, max_length=255, description="Street name", examples=["MG Road"])
    locality: Optional[str] = Field(None, max_length=255, description="Locality / area", examples=["Indiranagar"])
    ward: Optional[str] = Field(None, max_length=100, description="Ward number or name", examples=["Ward 74"])
    latitude: Optional[float] = Field(None, ge=-90, le=90, examples=[12.8012])
    longitude: Optional[float] = Field(None, ge=-180, le=180, examples=[77.6913])

    # Skills & qualification
    skill_category: str = Field(..., examples=["plumbing"])
    iti_nsqf_level: Optional[int] = Field(None, ge=1, le=5, examples=[3])
    highest_qualification: Optional[str] = Field(None, max_length=255, examples=["ITI Plumbing"])

    # Beckn person attributes
    languages: Optional[list[dict[str, str]]] = Field(
        None, description='e.g. [{"code":"en","name":"English"}]',
        examples=[[{"code": "en", "name": "English"}, {"code": "hi", "name": "Hindi"}]],
    )
    skills_detailed: Optional[list[dict[str, str]]] = Field(
        None, description='e.g. [{"code":"PLUMBER","name":"Plumber"}]',
        examples=[[{"code": "PLUMBER", "name": "Plumber"}]],
    )

    # Availability
    availability_status: str = Field("available", examples=["available"])
    preferred_shift: str = Field("flexible", examples=["morning"])
    fulfillment_type: str = Field("ONSITE", examples=["ONSITE"])

    # Verification — flexible JSON
    verification_status: Optional[dict[str, Any]] = Field(
        default_factory=dict,
        examples=[{"aadhaar_verified": True, "phone_verified": False, "phone_conversation": []}],
    )

    # Contact & experience
    phone: str = Field(..., max_length=15, examples=["+919876543210"])
    email: Optional[str] = Field(None, max_length=255, examples=["worker@example.com"])
    experience_years: Optional[float] = Field(None, ge=0, examples=[4.5])

    # Provenance
    source_channel: str = Field(..., examples=["telegram"])

    # ── Validators ──

    @field_validator("skill_category")
    @classmethod
    def validate_skill_category(cls, v: str) -> str:
        v_lower = v.lower()
        if v_lower not in SKILL_CATEGORIES:
            raise ValueError(f"Invalid skill_category. Allowed: {SKILL_CATEGORIES}")
        return v_lower

    @field_validator("source_channel")
    @classmethod
    def validate_source_channel(cls, v: str) -> str:
        v_lower = v.lower()
        if v_lower not in SOURCE_CHANNELS:
            raise ValueError(f"Invalid source_channel. Allowed: {SOURCE_CHANNELS}")
        return v_lower

    @field_validator("availability_status")
    @classmethod
    def validate_availability(cls, v: str) -> str:
        v_lower = v.lower()
        if v_lower not in AVAILABILITY_STATUSES:
            raise ValueError(f"Invalid availability_status. Allowed: {AVAILABILITY_STATUSES}")
        return v_lower

    @field_validator("preferred_shift")
    @classmethod
    def validate_shift(cls, v: str) -> str:
        v_lower = v.lower()
        if v_lower not in PREFERRED_SHIFTS:
            raise ValueError(f"Invalid preferred_shift. Allowed: {PREFERRED_SHIFTS}")
        return v_lower

    @field_validator("fulfillment_type")
    @classmethod
    def validate_fulfillment_type(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in FULFILLMENT_TYPES:
            raise ValueError(f"Invalid fulfillment_type. Allowed: {FULFILLMENT_TYPES}")
        return v_upper


# ── Response schemas ──────────────────────────


class WorkerStageOut(BaseModel):
    """Response schema returned after insert / upsert."""

    worker_id: str
    name: str
    dob: Optional[date] = None
    gender: Optional[str] = None
    aadhar_hash: str
    district: str
    taluk: Optional[str] = None
    city_village: Optional[str] = None
    state_name: Optional[str] = None
    state_code: Optional[str] = None
    city_code: Optional[str] = None
    area_code: Optional[str] = None
    door: Optional[str] = None
    building: Optional[str] = None
    street: Optional[str] = None
    locality: Optional[str] = None
    ward: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    skill_category: str
    iti_nsqf_level: Optional[int] = None
    highest_qualification: Optional[str] = None
    languages: Optional[list[dict[str, str]]] = None
    skills_detailed: Optional[list[dict[str, str]]] = None
    availability_status: str
    preferred_shift: str
    fulfillment_type: Optional[str] = None
    verification_status: Optional[dict[str, Any]] = None
    phone: str
    email: Optional[str] = None
    experience_years: Optional[float] = None
    source_channel: str
    status: str
    created_ts: datetime
    updated_ts: datetime

    model_config = {"from_attributes": True}


class UpsertResponse(BaseModel):
    """Response for the upsert endpoint — includes dedup info."""

    worker: WorkerStageOut
    duplicates_marked: int = Field(
        0, description="Number of previous records marked as old_duplicate"
    )
    is_new: bool = Field(True, description="True if no prior record existed for this aadhar_hash")


class WorkerStageSearchResponse(BaseModel):
    """Paginated search response."""

    total: int = Field(..., description="Total matching records")
    page: int
    page_size: int
    results: list[WorkerStageOut]


class DeleteResponse(BaseModel):
    """Response for the filtered delete endpoint."""

    dry_run: bool = Field(..., description="True = preview only, nothing was deleted")
    matched: int = Field(..., description="Number of records matching the filters")
    deleted: int = Field(0, description="Number of records actually deleted (0 if dry_run)")
