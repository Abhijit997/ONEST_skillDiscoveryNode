"""
SQLAlchemy ORM models for the worker_stage table and Beckn protocol tables.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
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


class FulfillmentType(str, enum.Enum):
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    ONSITE = "ONSITE"


class FulfillmentStatusCode(str, enum.Enum):
    APPLICATION_STARTED = "APPLICATION-STARTED"
    APPLICATION_FILLED = "APPLICATION-FILLED"
    UNDER_REVIEW = "UNDER-REVIEW"
    OFFER_EXTENDED = "OFFER-EXTENDED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class OrderState(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"


# ── Model ─────────────────────────────────────


def _generate_uuid() -> str:
    return str(uuid.uuid4())


class WorkerStage(Base):
    __tablename__ = "worker_stage"

    worker_id = Column(String(36), primary_key=True, default=_generate_uuid)
    name = Column(String(255), nullable=False)
    dob = Column(Date, nullable=True)  # Date of birth
    gender = Column(String(20), nullable=True)  # Male / Female / Other
    aadhar_hash = Column(String(64), nullable=False, index=True)  # SHA-256 hex

    # Location
    district = Column(String(255), nullable=False)
    taluk = Column(String(255), nullable=True)
    city_village = Column(String(255), nullable=True)
    state_name = Column(String(255), nullable=True)  # Beckn: state.name
    state_code = Column(String(10), nullable=True)   # Beckn: ISO state code e.g. "KA"
    city_code = Column(String(20), nullable=True)     # Beckn: STD code e.g. "std:080"
    area_code = Column(String(10), nullable=True)     # PIN/ZIP code e.g. "560001"
    door = Column(String(100), nullable=True)         # Door / flat number
    building = Column(String(255), nullable=True)     # Building / apartment name
    street = Column(String(255), nullable=True)       # Street name
    locality = Column(String(255), nullable=True)     # Locality / area
    ward = Column(String(100), nullable=True)         # Ward number / name
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Skills & qualification
    skill_category = Column(Enum(SkillCategory), nullable=False)
    iti_nsqf_level = Column(Integer, nullable=True)  # 1-5
    highest_qualification = Column(String(255), nullable=True)

    # Beckn-required person attributes
    languages = Column(JSON, nullable=True)  # [{"code":"en","name":"English"},...]
    skills_detailed = Column(JSON, nullable=True)  # [{"code":"PLUMBER","name":"Plumber"},...]

    # Availability
    availability_status = Column(
        Enum(AvailabilityStatus), default=AvailabilityStatus.AVAILABLE
    )
    preferred_shift = Column(Enum(PreferredShift), default=PreferredShift.FLEXIBLE)

    # Beckn fulfillment
    fulfillment_type = Column(
        Enum(FulfillmentType), default=FulfillmentType.ONSITE
    )

    # Verification — flexible JSON for evolving fields
    verification_status = Column(JSON, default=dict)

    # Contact & experience
    phone = Column(String(15), nullable=False)
    email = Column(String(255), nullable=True)
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


# ── Beckn Order tracking ─────────────────────


class BecknOrder(Base):
    """Tracks Beckn transaction lifecycle (select → init → confirm → status)."""
    __tablename__ = "beckn_order"

    order_id = Column(String(36), primary_key=True, default=_generate_uuid)
    transaction_id = Column(String(100), nullable=False, index=True, unique=True)
    message_id = Column(String(100), nullable=True)

    # BAP identity
    bap_id = Column(String(255), nullable=False)
    bap_uri = Column(String(500), nullable=False)

    # Worker / item being applied for
    worker_id = Column(String(36), ForeignKey("worker_stage.worker_id"), nullable=True)
    item_id = Column(String(255), nullable=True)
    provider_id = Column(String(255), nullable=True)

    # Order state
    state = Column(Enum(OrderState), default=OrderState.DRAFT)

    # Fulfillment state machine
    fulfillment_status = Column(
        Enum(FulfillmentStatusCode),
        default=FulfillmentStatusCode.APPLICATION_STARTED,
    )
    fulfillment_type = Column(Enum(FulfillmentType), default=FulfillmentType.ONSITE)

    # Customer (applicant) info  — JSON blob
    customer_person = Column(JSON, nullable=True)
    customer_contact = Column(JSON, nullable=True)

    # Billing info — JSON blob
    billing = Column(JSON, nullable=True)

    # xInput tracking
    xinput_required = Column(Integer, default=0)  # total number of forms
    xinput_submitted = Column(Integer, default=0)  # forms completed so far

    # Cancellation
    cancellation_reason = Column(Text, nullable=True)

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

    def __repr__(self) -> str:
        return (
            f"<BecknOrder {self.order_id} txn={self.transaction_id} "
            f"state={self.state} fulfillment={self.fulfillment_status}>"
        )


class XInputForm(Base):
    """Tracks xInput form steps for a Beckn order."""
    __tablename__ = "xinput_form"

    form_id = Column(String(36), primary_key=True, default=_generate_uuid)
    order_id = Column(
        String(36), ForeignKey("beckn_order.order_id"), nullable=False, index=True
    )
    transaction_id = Column(String(100), nullable=False, index=True)
    step_index = Column(Integer, nullable=False, default=0)  # 0-based
    heading = Column(String(255), nullable=True)
    form_data = Column(JSON, nullable=True)  # submitted data
    submitted = Column(Integer, default=0)  # 0=pending, 1=submitted
    created_ts = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<XInputForm {self.form_id} step={self.step_index} submitted={self.submitted}>"
