"""
Worker Stage API routes.

GET  /workers/stage/search   — search / filter workers
POST /workers/stage          — plain insert
POST /workers/stage/upsert   — insert + mark previous duplicates as old_duplicate
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.schemas import (
    DeleteResponse,
    UpsertResponse,
    WorkerCreate,
    WorkerOut,
    WorkerSearchResponse,
)
from app.db.database import get_db
from app.db.models import Worker, WorkerStatus
from app.services.geocode import geocode_pincode

router = APIRouter(prefix="/workers", tags=["workers"])


def _create_worker_record(payload: WorkerCreate) -> Worker:
    """Map validated Pydantic model → ORM instance.

    If latitude/longitude or state are not supplied but area_code (PIN/ZIP)
    is present, we attempt an offline geocode lookup via pgeocode.  State
    codes are always stored as ISO 3166-2:IN (e.g. 'KA', 'MH').
    """
    lat = payload.latitude
    lon = payload.longitude
    s_name = payload.state_name
    s_code = payload.state_code

    # Auto-fill from PIN code when fields are missing
    if payload.area_code and (lat is None or lon is None or not s_name or not s_code):
        geo = geocode_pincode(payload.area_code)
        if geo:
            lat = lat if lat is not None else geo.latitude
            lon = lon if lon is not None else geo.longitude
            s_name = s_name or geo.state_name
            s_code = s_code or geo.state_code

    return Worker(
        name=payload.name,
        aadhar_hash=payload.aadhar_hash.lower(),  # normalise hex to lowercase
        district=payload.district,
        taluk=payload.taluk,
        city_village=payload.city_village,
        state_name=s_name,
        state_code=s_code,
        area_code=payload.area_code,
        door=payload.door,
        building=payload.building,
        street=payload.street,
        locality=payload.locality,
        ward=payload.ward,
        latitude=lat,
        longitude=lon,
        skill_category=payload.skill_category,
        iti_nsqf_level=payload.iti_nsqf_level,
        highest_qualification=payload.highest_qualification,
        availability_status=payload.availability_status,
        preferred_shift=payload.preferred_shift,
        verification_status=payload.verification_status or {},
        phone=payload.phone,
        experience_years=payload.experience_years,
        source_channel=payload.source_channel,
        status=WorkerStatus.ACTIVE,
    )


# ── Shared filter builder ─────────────────────


def _apply_filters(
    q,
    *,
    worker_id: Optional[str] = None,
    name: Optional[str] = None,
    district: Optional[str] = None,
    city_village: Optional[str] = None,
    skill_category: Optional[str] = None,
    iti_nsqf_level: Optional[int] = None,
    highest_qualification: Optional[str] = None,
    availability_status: Optional[str] = None,
    preferred_shift: Optional[str] = None,
    phone: Optional[str] = None,
    experience_years_min: Optional[float] = None,
    experience_years_max: Optional[float] = None,
    source_channel: Optional[str] = None,
    status: Optional[str] = None,
    created_ts_from: Optional[datetime] = None,
    created_ts_to: Optional[datetime] = None,
    updated_ts_from: Optional[datetime] = None,
    updated_ts_to: Optional[datetime] = None,
):
    """Apply all optional filters to a Worker query and return it."""
    # Exact matches
    if worker_id:
        q = q.filter(Worker.worker_id == worker_id)
    if skill_category:
        q = q.filter(Worker.skill_category == skill_category.lower())
    if iti_nsqf_level is not None:
        q = q.filter(Worker.iti_nsqf_level == iti_nsqf_level)
    if availability_status:
        q = q.filter(Worker.availability_status == availability_status.lower())
    if preferred_shift:
        q = q.filter(Worker.preferred_shift == preferred_shift.lower())
    if source_channel:
        q = q.filter(Worker.source_channel == source_channel.lower())
    if status:
        q = q.filter(Worker.status == status.lower())

    # Partial / LIKE matches (case-insensitive)
    if name:
        q = q.filter(Worker.name.ilike(f"%{name}%"))
    if district:
        q = q.filter(Worker.district.ilike(f"%{district}%"))
    if city_village:
        q = q.filter(Worker.city_village.ilike(f"%{city_village}%"))
    if highest_qualification:
        q = q.filter(Worker.highest_qualification.ilike(f"%{highest_qualification}%"))
    if phone:
        q = q.filter(Worker.phone.ilike(f"%{phone}%"))

    # Range filters
    if experience_years_min is not None:
        q = q.filter(Worker.experience_years >= experience_years_min)
    if experience_years_max is not None:
        q = q.filter(Worker.experience_years <= experience_years_max)
    if created_ts_from:
        q = q.filter(Worker.created_ts >= created_ts_from)
    if created_ts_to:
        q = q.filter(Worker.created_ts <= created_ts_to)
    if updated_ts_from:
        q = q.filter(Worker.updated_ts >= updated_ts_from)
    if updated_ts_to:
        q = q.filter(Worker.updated_ts <= updated_ts_to)

    return q


# ── 1. Search / filter ────────────────────────


@router.get(
    "/stage/search",
    response_model=WorkerSearchResponse,
    summary="Search worker records",
    description=(
        "Flexible search with all-optional query parameters. "
        "All text filters are case-insensitive partial matches (LIKE). "
        "Supports pagination via `page` and `page_size`."
    ),
)
def search_workers(
    worker_id: Optional[str] = Query(None, description="Exact worker UUID"),
    name: Optional[str] = Query(None, description="Partial name match (case-insensitive)"),
    district: Optional[str] = Query(None, description="Partial district match"),
    city_village: Optional[str] = Query(None, description="Partial city/village match"),
    skill_category: Optional[str] = Query(None, description="Exact skill category"),
    iti_nsqf_level: Optional[int] = Query(None, ge=1, le=5, description="NSQF level 1-5"),
    highest_qualification: Optional[str] = Query(None, description="Partial qualification match"),
    availability_status: Optional[str] = Query(None, description="Exact availability status"),
    preferred_shift: Optional[str] = Query(None, description="Exact preferred shift"),
    phone: Optional[str] = Query(None, description="Partial phone match"),
    experience_years_min: Optional[float] = Query(None, ge=0, description="Minimum experience years"),
    experience_years_max: Optional[float] = Query(None, ge=0, description="Maximum experience years"),
    source_channel: Optional[str] = Query(None, description="Exact source channel"),
    status: Optional[str] = Query(None, description="Exact worker status"),
    created_ts_from: Optional[datetime] = Query(None, description="Created after (ISO 8601)"),
    created_ts_to: Optional[datetime] = Query(None, description="Created before (ISO 8601)"),
    updated_ts_from: Optional[datetime] = Query(None, description="Updated after (ISO 8601)"),
    updated_ts_to: Optional[datetime] = Query(None, description="Updated before (ISO 8601)"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page (max 100)"),
    db: Session = Depends(get_db),
):
    q = _apply_filters(
        db.query(Worker),
        worker_id=worker_id, name=name, district=district,
        city_village=city_village, skill_category=skill_category,
        iti_nsqf_level=iti_nsqf_level, highest_qualification=highest_qualification,
        availability_status=availability_status, preferred_shift=preferred_shift,
        phone=phone, experience_years_min=experience_years_min,
        experience_years_max=experience_years_max, source_channel=source_channel,
        status=status, created_ts_from=created_ts_from, created_ts_to=created_ts_to,
        updated_ts_from=updated_ts_from, updated_ts_to=updated_ts_to,
    )

    total = q.count()
    results = (
        q.order_by(Worker.created_ts.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return WorkerSearchResponse(
        total=total,
        page=page,
        page_size=page_size,
        results=[WorkerOut.model_validate(r) for r in results],
    )


# ── 2. Plain insert ──────────────────────────


@router.post(
    "/stage",
    response_model=WorkerOut,
    status_code=http_status.HTTP_201_CREATED,
    summary="Insert a new worker record",
    description="Straight insert — does NOT perform dedup. Use /stage/upsert for dedup behaviour.",
)
def insert_worker(payload: WorkerCreate, db: Session = Depends(get_db)):
    record = _create_worker_record(payload)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ── 3. Upsert (insert + mark previous duplicates) ─


@router.post(
    "/stage/upsert",
    response_model=UpsertResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Insert worker & mark previous duplicates",
    description=(
        "Inserts a new worker record. If any previous records share the same "
        "aadhar_hash and have an ACTIVE status, their status is updated to 'old_duplicate'. "
        "Returns the new record and a count of how many duplicates were marked."
    ),
)
def upsert_worker(payload: WorkerCreate, db: Session = Depends(get_db)):
    aadhar_normalised = payload.aadhar_hash.lower()

    # Mark existing active records for this aadhar_hash as old_duplicate
    now = datetime.now(timezone.utc)
    updated_count = (
        db.query(Worker)
        .filter(
            Worker.aadhar_hash == aadhar_normalised,
            Worker.status != WorkerStatus.OLD_DUPLICATE,
        )
        .update(
            {
                Worker.status: WorkerStatus.OLD_DUPLICATE,
                Worker.updated_ts: now,
            },
            synchronize_session="fetch",
        )
    )

    # Insert the new record
    record = _create_worker_record(payload)
    db.add(record)
    db.commit()
    db.refresh(record)

    return UpsertResponse(
        worker=WorkerOut.model_validate(record),
        duplicates_marked=updated_count,
        is_new=(updated_count == 0),
    )


# ── 4. Filtered delete (with dry-run) ─────────


@router.delete(
    "/stage",
    response_model=DeleteResponse,
    summary="Delete worker records by filter",
    description=(
        "Deletes records matching the same filters as the search endpoint. "
        "Defaults to dry_run=true (preview only). Set dry_run=false to actually delete. "
        "At least one filter must be provided to prevent accidental full-table deletes."
    ),
)
def delete_workers(
    worker_id: Optional[str] = Query(None, description="Exact worker UUID"),
    name: Optional[str] = Query(None, description="Partial name match (case-insensitive)"),
    district: Optional[str] = Query(None, description="Partial district match"),
    city_village: Optional[str] = Query(None, description="Partial city/village match"),
    skill_category: Optional[str] = Query(None, description="Exact skill category"),
    iti_nsqf_level: Optional[int] = Query(None, ge=1, le=5, description="NSQF level 1-5"),
    highest_qualification: Optional[str] = Query(None, description="Partial qualification match"),
    availability_status: Optional[str] = Query(None, description="Exact availability status"),
    preferred_shift: Optional[str] = Query(None, description="Exact preferred shift"),
    phone: Optional[str] = Query(None, description="Partial phone match"),
    experience_years_min: Optional[float] = Query(None, ge=0, description="Minimum experience years"),
    experience_years_max: Optional[float] = Query(None, ge=0, description="Maximum experience years"),
    source_channel: Optional[str] = Query(None, description="Exact source channel"),
    status: Optional[str] = Query(None, description="Exact worker status"),
    created_ts_from: Optional[datetime] = Query(None, description="Created after (ISO 8601)"),
    created_ts_to: Optional[datetime] = Query(None, description="Created before (ISO 8601)"),
    updated_ts_from: Optional[datetime] = Query(None, description="Updated after (ISO 8601)"),
    updated_ts_to: Optional[datetime] = Query(None, description="Updated before (ISO 8601)"),
    dry_run: bool = Query(True, description="True = preview only; False = actually delete"),
    db: Session = Depends(get_db),
):
    # Safety: require at least one filter
    has_filter = any([
        worker_id, name, district, city_village, skill_category,
        iti_nsqf_level is not None, highest_qualification, availability_status,
        preferred_shift, phone, experience_years_min is not None,
        experience_years_max is not None, source_channel, status,
        created_ts_from, created_ts_to, updated_ts_from, updated_ts_to,
    ])
    if not has_filter:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="At least one filter parameter is required to prevent accidental full-table delete.",
        )

    q = _apply_filters(
        db.query(Worker),
        worker_id=worker_id, name=name, district=district,
        city_village=city_village, skill_category=skill_category,
        iti_nsqf_level=iti_nsqf_level, highest_qualification=highest_qualification,
        availability_status=availability_status, preferred_shift=preferred_shift,
        phone=phone, experience_years_min=experience_years_min,
        experience_years_max=experience_years_max, source_channel=source_channel,
        status=status, created_ts_from=created_ts_from, created_ts_to=created_ts_to,
        updated_ts_from=updated_ts_from, updated_ts_to=updated_ts_to,
    )

    matched = q.count()

    if dry_run:
        return DeleteResponse(dry_run=True, matched=matched, deleted=0)

    deleted = q.delete(synchronize_session="fetch")
    db.commit()

    return DeleteResponse(dry_run=False, matched=matched, deleted=deleted)
