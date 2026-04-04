"""
CRUD API for the beckn_order table.

Thin HTTP layer — all DB logic lives in ``app.services.order_service``.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status

from app.db.database import SessionLocal
from app.api.schemas import (
    BecknOrderCreate,
    BecknOrderUpdate,
    BecknOrderOut,
    BecknOrderListResponse,
    DeleteResponse,
)
from app.services.order_service import (
    get_order_by_id,
    get_order_by_txn,
    list_orders as svc_list_orders,
    create_order as svc_create_order,
    update_order as svc_update_order,
    delete_order as svc_delete_order,
)

router = APIRouter(prefix="/orders", tags=["beckn_order"])


# ── List / search ─────────────────────────────


@router.get("", response_model=BecknOrderListResponse)
def list_orders(
    state: Optional[str] = Query(None, description="Filter by order state"),
    bap_id: Optional[str] = Query(None, description="Filter by BAP ID"),
    worker_id: Optional[str] = Query(None, description="Filter by worker ID"),
    transaction_id: Optional[str] = Query(None, description="Filter by transaction ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Return a paginated list of Beckn orders with optional filters."""
    with SessionLocal() as db:
        total, rows = svc_list_orders(
            db,
            state=state,
            bap_id=bap_id,
            worker_id=worker_id,
            transaction_id=transaction_id,
            page=page,
            page_size=page_size,
        )
    return BecknOrderListResponse(
        total=total, page=page, page_size=page_size, results=rows
    )


# ── Get by ID ─────────────────────────────────


@router.get("/{order_id}", response_model=BecknOrderOut)
def get_order(order_id: str):
    """Retrieve a single Beckn order by its order_id."""
    with SessionLocal() as db:
        order = get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


# ── Create ────────────────────────────────────


@router.post("", response_model=BecknOrderOut, status_code=http_status.HTTP_201_CREATED)
def create_order(payload: BecknOrderCreate):
    """Create a new Beckn order."""
    with SessionLocal() as db:
        if get_order_by_txn(db, payload.transaction_id):
            raise HTTPException(
                http_status.HTTP_409_CONFLICT,
                detail=f"Order with transaction_id '{payload.transaction_id}' already exists",
            )
        order = svc_create_order(db, **payload.model_dump())
    return order


# ── Update (partial) ─────────────────────────


@router.patch("/{order_id}", response_model=BecknOrderOut)
def update_order(order_id: str, payload: BecknOrderUpdate):
    """Partially update an existing Beckn order."""
    with SessionLocal() as db:
        order = get_order_by_id(db, order_id)
        if not order:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail="Order not found")

        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST, detail="No fields to update"
            )
        order = svc_update_order(db, order, **update_data)
    return order


# ── Delete ────────────────────────────────────


@router.delete("/{order_id}", response_model=DeleteResponse)
def delete_order(order_id: str, dry_run: bool = Query(True)):
    """Delete a Beckn order by its order_id. Use dry_run=false to confirm."""
    with SessionLocal() as db:
        order = get_order_by_id(db, order_id)
        if not order:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail="Order not found")

        if dry_run:
            return DeleteResponse(dry_run=True, matched=1, deleted=0)

        svc_delete_order(db, order)
    return DeleteResponse(dry_run=False, matched=1, deleted=1)
