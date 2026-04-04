"""
Service layer for beckn_order table operations.

All DB queries/mutations for BecknOrder live here.  Both the CRUD API
(``app.api.orders``) and the Beckn protocol layer (``app.api.bpp``)
import from this module — single source of truth.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import BecknOrder

log = logging.getLogger(__name__)


# ── Reads ─────────────────────────────────────


def get_order_by_id(db: Session, order_id: str) -> BecknOrder | None:
    """Fetch a single order by primary key."""
    return db.query(BecknOrder).filter(BecknOrder.order_id == order_id).first()


def get_order_by_txn(db: Session, transaction_id: str) -> BecknOrder | None:
    """Fetch a single order by its unique transaction_id."""
    return db.query(BecknOrder).filter(BecknOrder.transaction_id == transaction_id).first()


def find_order(
    db: Session,
    *,
    order_id: str | None = None,
    transaction_id: str | None = None,
) -> BecknOrder | None:
    """Try to locate an order — prefers order_id, falls back to transaction_id."""
    if order_id:
        return get_order_by_id(db, order_id)
    if transaction_id:
        return get_order_by_txn(db, transaction_id)
    return None


def list_orders(
    db: Session,
    *,
    state: str | None = None,
    bap_id: str | None = None,
    worker_id: str | None = None,
    transaction_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[int, list[BecknOrder]]:
    """Return (total_count, page_of_rows) with optional filters."""
    q = db.query(BecknOrder)
    if state:
        q = q.filter(BecknOrder.state == state.upper())
    if bap_id:
        q = q.filter(BecknOrder.bap_id == bap_id)
    if worker_id:
        q = q.filter(BecknOrder.worker_id == worker_id)
    if transaction_id:
        q = q.filter(BecknOrder.transaction_id == transaction_id)

    total = q.count()
    rows = (
        q.order_by(BecknOrder.created_ts.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return total, rows


# ── Writes ────────────────────────────────────


def create_order(db: Session, **kwargs: Any) -> BecknOrder:
    """Insert a new BecknOrder row and return it (flushed + refreshed)."""
    order = BecknOrder(**kwargs)
    db.add(order)
    db.commit()
    db.refresh(order)
    log.info("Created order %s (txn=%s)", order.order_id, order.transaction_id)
    return order


def update_order(db: Session, order: BecknOrder, **kwargs: Any) -> BecknOrder:
    """Apply a dict of field updates to an existing order row."""
    for key, value in kwargs.items():
        setattr(order, key, value)
    db.commit()
    db.refresh(order)
    log.info("Updated order %s — fields: %s", order.order_id, list(kwargs.keys()))
    return order


def delete_order(db: Session, order: BecknOrder) -> None:
    """Hard-delete an order row."""
    oid = order.order_id
    db.delete(order)
    db.commit()
    log.info("Deleted order %s", oid)
