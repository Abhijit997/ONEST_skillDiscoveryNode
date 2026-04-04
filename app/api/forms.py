"""
CRUD API for the xinput_form table.

Thin HTTP layer — all DB logic lives in ``app.services.form_service``.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status

from app.db.database import SessionLocal
from app.api.schemas import (
    XInputFormCreate,
    XInputFormUpdate,
    XInputFormOut,
    XInputFormListResponse,
    DeleteResponse,
)
from app.services.form_service import (
    get_form_by_id,
    list_forms as svc_list_forms,
    create_form as svc_create_form,
    update_form as svc_update_form,
    delete_form as svc_delete_form,
)

router = APIRouter(prefix="/xinput-forms", tags=["xinput_form"])


# ── List / search ─────────────────────────────


@router.get("", response_model=XInputFormListResponse)
def list_forms(
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    transaction_id: Optional[str] = Query(None, description="Filter by transaction ID"),
    submitted: Optional[int] = Query(None, ge=0, le=1, description="0=pending, 1=submitted"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Return a paginated list of xInput form steps with optional filters."""
    with SessionLocal() as db:
        total, rows = svc_list_forms(
            db,
            order_id=order_id,
            transaction_id=transaction_id,
            submitted=submitted,
            page=page,
            page_size=page_size,
        )
    return XInputFormListResponse(
        total=total, page=page, page_size=page_size, results=rows
    )


# ── Get by ID ─────────────────────────────────


@router.get("/{form_id}", response_model=XInputFormOut)
def get_form(form_id: str):
    """Retrieve a single xInput form step by its form_id."""
    with SessionLocal() as db:
        form = get_form_by_id(db, form_id)
    if not form:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail="Form not found")
    return form


# ── Create ────────────────────────────────────


@router.post("", response_model=XInputFormOut, status_code=http_status.HTTP_201_CREATED)
def create_form(payload: XInputFormCreate):
    """Create a new xInput form step."""
    with SessionLocal() as db:
        form = svc_create_form(db, **payload.model_dump())
    return form


# ── Update (partial) ─────────────────────────


@router.patch("/{form_id}", response_model=XInputFormOut)
def update_form(form_id: str, payload: XInputFormUpdate):
    """Partially update an existing xInput form step."""
    with SessionLocal() as db:
        form = get_form_by_id(db, form_id)
        if not form:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail="Form not found")

        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST, detail="No fields to update"
            )
        form = svc_update_form(db, form, **update_data)
    return form


# ── Delete ────────────────────────────────────


@router.delete("/{form_id}", response_model=DeleteResponse)
def delete_form(form_id: str, dry_run: bool = Query(True)):
    """Delete an xInput form step by its form_id. Use dry_run=false to confirm."""
    with SessionLocal() as db:
        form = get_form_by_id(db, form_id)
        if not form:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail="Form not found")

        if dry_run:
            return DeleteResponse(dry_run=True, matched=1, deleted=0)

        svc_delete_form(db, form)
    return DeleteResponse(dry_run=False, matched=1, deleted=1)
