"""
Pydantic request / response schemas for the worker_stage API.
"""

from datetime import datetime
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


# ── Request schemas ───────────────────────────


class WorkerStageCreate(BaseModel):
    """Payload for inserting a new worker_stage record."""

    name: str = Field(..., min_length=1, max_length=255, examples=["Ramesh Kumar"])
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
    latitude: Optional[float] = Field(None, ge=-90, le=90, examples=[12.8012])
    longitude: Optional[float] = Field(None, ge=-180, le=180, examples=[77.6913])

    # Skills & qualification
    skill_category: str = Field(..., examples=["plumbing"])
    iti_nsqf_level: Optional[int] = Field(None, ge=1, le=5, examples=[3])
    highest_qualification: Optional[str] = Field(None, max_length=255, examples=["ITI Plumbing"])

    # Availability
    availability_status: str = Field("available", examples=["available"])
    preferred_shift: str = Field("flexible", examples=["morning"])

    # Verification — flexible JSON
    verification_status: Optional[dict[str, Any]] = Field(
        default_factory=dict,
        examples=[{"aadhaar_verified": True, "phone_verified": True}],
    )

    # Contact & experience
    phone: str = Field(..., max_length=15, examples=["+919876543210"])
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


# ── Response schemas ──────────────────────────


class WorkerStageOut(BaseModel):
    """Response schema returned after insert / upsert."""

    worker_id: str
    name: str
    aadhar_hash: str
    district: str
    taluk: Optional[str] = None
    city_village: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    skill_category: str
    iti_nsqf_level: Optional[int] = None
    highest_qualification: Optional[str] = None
    availability_status: str
    preferred_shift: str
    verification_status: Optional[dict[str, Any]] = None
    phone: str
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
