"""
Service layer for xinput_form table operations.

All DB queries/mutations for XInputForm live here.  Both the CRUD API
(``app.api.forms``) and the Beckn/xInput layers (``app.api.bpp``,
``app.api.xinput``) import from this module — single source of truth.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import XInputForm

log = logging.getLogger(__name__)


# ── Reads ─────────────────────────────────────


def get_form_by_id(db: Session, form_id: str) -> XInputForm | None:
    """Fetch a single form step by primary key."""
    return db.query(XInputForm).filter(XInputForm.form_id == form_id).first()


def get_form_by_order_step(
    db: Session, order_id: str, step_index: int
) -> XInputForm | None:
    """Fetch a form step by (order_id, step_index) pair."""
    return (
        db.query(XInputForm)
        .filter_by(order_id=order_id, step_index=step_index)
        .first()
    )


def get_forms_by_order(db: Session, order_id: str) -> list[XInputForm]:
    """Return all form steps for an order, sorted by step_index."""
    return (
        db.query(XInputForm)
        .filter_by(order_id=order_id)
        .order_by(XInputForm.step_index)
        .all()
    )


def count_submitted_forms(db: Session, order_id: str) -> int:
    """Return how many form steps have been submitted for an order."""
    return (
        db.query(XInputForm)
        .filter_by(order_id=order_id, submitted=1)
        .count()
    )


def list_forms(
    db: Session,
    *,
    order_id: str | None = None,
    transaction_id: str | None = None,
    submitted: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[int, list[XInputForm]]:
    """Return (total_count, page_of_rows) with optional filters."""
    q = db.query(XInputForm)
    if order_id:
        q = q.filter(XInputForm.order_id == order_id)
    if transaction_id:
        q = q.filter(XInputForm.transaction_id == transaction_id)
    if submitted is not None:
        q = q.filter(XInputForm.submitted == submitted)

    total = q.count()
    rows = (
        q.order_by(XInputForm.created_ts.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return total, rows


# ── Writes ────────────────────────────────────


def create_form(db: Session, **kwargs: Any) -> XInputForm:
    """Insert a new XInputForm row and return it (flushed + refreshed)."""
    form = XInputForm(**kwargs)
    db.add(form)
    db.commit()
    db.refresh(form)
    log.info(
        "Created xinput_form %s (order=%s, step=%d)",
        form.form_id, form.order_id, form.step_index,
    )
    return form


def update_form(db: Session, form: XInputForm, **kwargs: Any) -> XInputForm:
    """Apply a dict of field updates to an existing form row."""
    for key, value in kwargs.items():
        setattr(form, key, value)
    db.commit()
    db.refresh(form)
    log.info("Updated xinput_form %s — fields: %s", form.form_id, list(kwargs.keys()))
    return form


def delete_form(db: Session, form: XInputForm) -> None:
    """Hard-delete a form row."""
    fid = form.form_id
    db.delete(form)
    db.commit()
    log.info("Deleted xinput_form %s", fid)
