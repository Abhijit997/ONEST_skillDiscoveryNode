"""
SQLAlchemy ORM model for the worker_stage table.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from app.db.database import Base


# ── Enums ─────────────────────────────────────


class SkillCategory(str, enum.Enum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    CARPENTRY = "carpentry"
    WELDING = "welding"
    MASONRY = "masonry"
    PAINTING = "painting"
    HVAC = "hvac"
    TAILORING = "tailoring"
    DRIVING = "driving"
    COOKING = "cooking"
    HOUSEKEEPING = "housekeeping"
    GARDENING = "gardening"
    SECURITY = "security"
    DELIVERY = "delivery"
    CONSTRUCTION = "construction"
    MECHANIC = "mechanic"
    BEAUTY = "beauty"
    OTHER = "other"


class SourceChannel(str, enum.Enum):
    CSV = "csv"
    TELEGRAM = "telegram"
    CHAT_SIMULATOR = "chat_simulator"
    API = "api"
    MANUAL = "manual"


class WorkerStatus(str, enum.Enum):
    ACTIVE = "active"
    OLD_DUPLICATE = "old_duplicate"
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    REJECTED = "rejected"
    INACTIVE = "inactive"


class AvailabilityStatus(str, enum.Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PARTIALLY_AVAILABLE = "partially_available"


class PreferredShift(str, enum.Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"
    FLEXIBLE = "flexible"


# ── Model ─────────────────────────────────────


def _generate_uuid() -> str:
    return str(uuid.uuid4())


class WorkerStage(Base):
    __tablename__ = "worker_stage"

    worker_id = Column(String(36), primary_key=True, default=_generate_uuid)
    name = Column(String(255), nullable=False)
    aadhar_hash = Column(String(64), nullable=False, index=True)  # SHA-256 hex

    # Location
    district = Column(String(255), nullable=False)
    taluk = Column(String(255), nullable=True)
    city_village = Column(String(255), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Skills & qualification
    skill_category = Column(Enum(SkillCategory), nullable=False)
    iti_nsqf_level = Column(Integer, nullable=True)  # 1-5
    highest_qualification = Column(String(255), nullable=True)

    # Availability
    availability_status = Column(
        Enum(AvailabilityStatus), default=AvailabilityStatus.AVAILABLE
    )
    preferred_shift = Column(Enum(PreferredShift), default=PreferredShift.FLEXIBLE)

    # Verification — flexible JSON for evolving fields
    verification_status = Column(JSON, default=dict)

    # Contact & experience
    phone = Column(String(15), nullable=False)
    experience_years = Column(Float, nullable=True)

    # Provenance
    source_channel = Column(Enum(SourceChannel), nullable=False)
    status = Column(
        Enum(WorkerStatus), nullable=False, default=WorkerStatus.ACTIVE
    )

    # Timestamps
    created_ts = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_ts = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Composite index for dedup queries
    __table_args__ = (
        Index("ix_worker_stage_aadhar_status", "aadhar_hash", "status"),
    )

    def __repr__(self) -> str:
        return f"<WorkerStage {self.worker_id} name={self.name!r} status={self.status}>"
