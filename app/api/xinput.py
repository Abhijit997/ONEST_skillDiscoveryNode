"""
xInput Form Hosting Endpoints
==============================

Serves and accepts xInput forms as required by the ONEST init/confirm flow.

Each Beckn order can require N form steps. The BPP tells the BAP the form URL
in the ``on_init`` / ``on_select`` payload, and the BAP (or user agent) GETs
the form page and POSTs the submission.

Endpoints:
    GET  /api/xinput/form/{order_id}/{step}          — render form (HTML)
    POST /api/xinput/form/{order_id}/{step}/submit    — submit form data (JSON)
    GET  /api/xinput/status/{order_id}                — check all steps' status
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import BecknOrder, XInputForm

log = logging.getLogger(__name__)

router = APIRouter(prefix="/xinput", tags=["xinput-forms"])


# ── Request / Response schemas ────────────────


class FormSubmission(BaseModel):
    """Payload POSTed by the user agent when submitting a form step."""
    data: dict  # free-form JSON matching the form fields


class FormStatusOut(BaseModel):
    form_id: str
    step_index: int
    heading: str | None
    submitted: bool
    form_data: dict | None = None


class OrderFormStatus(BaseModel):
    order_id: str
    total_steps: int
    submitted_steps: int
    steps: list[FormStatusOut]


# ── GET  /form/{order_id}/{step} — serve form page ─────


@router.get("/form/{order_id}/{step}", response_class=HTMLResponse)
async def get_form(order_id: str, step: int, db: Session = Depends(get_db)):
    """Return a simple HTML form for the given step of the given order."""
    db_order = db.query(BecknOrder).filter_by(order_id=order_id).first()
    if not db_order:
        raise HTTPException(404, "Order not found")

    form_row = (
        db.query(XInputForm)
        .filter_by(order_id=order_id, step_index=step)
        .first()
    )
    if not form_row:
        raise HTTPException(404, f"Form step {step} not found for order {order_id}")

    heading = form_row.heading or f"Step {step}"
    already = "✅ Already submitted" if form_row.submitted else ""

    # Build a minimal self-posting HTML form
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{heading}</title>
<style>
  body {{ font-family: sans-serif; max-width: 600px; margin: 2rem auto; }}
  label {{ display: block; margin-top: 1rem; font-weight: bold; }}
  input, textarea {{ width: 100%; padding: .5rem; }}
  button {{ margin-top: 1.5rem; padding: .75rem 2rem; }}
</style>
</head>
<body>
<h2>{heading}</h2>
<p>Order: <code>{order_id}</code> &nbsp; Step {step + 1} of {db_order.xinput_required}</p>
<p style="color:green">{already}</p>
<form id="xform">
"""

    if step == 0:
        # Personal details form
        html += """
  <label>Full Name <input name="full_name" required></label>
  <label>Date of Birth <input name="dob" type="date" required></label>
  <label>Gender
    <select name="gender">
      <option value="Male">Male</option>
      <option value="Female">Female</option>
      <option value="Other">Other</option>
    </select>
  </label>
  <label>Phone <input name="phone" type="tel" required></label>
  <label>Email <input name="email" type="email"></label>
  <label>Address <textarea name="address" rows="2"></textarea></label>
"""
    elif step == 1:
        # Document upload (mock — just text fields for URLs)
        html += """
  <label>Aadhaar Document URL <input name="aadhaar_doc_url" placeholder="https://..."></label>
  <label>Resume URL <input name="resume_url" placeholder="https://..."></label>
  <label>Additional Notes <textarea name="notes" rows="3"></textarea></label>
"""
    else:
        html += f'  <label>Data <textarea name="data" rows="4"></textarea></label>\n'

    html += f"""
  <button type="submit">Submit Step {step + 1}</button>
</form>
<script>
document.getElementById('xform').addEventListener('submit', async e => {{
  e.preventDefault();
  const fd = new FormData(e.target);
  const data = Object.fromEntries(fd.entries());
  const resp = await fetch('/api/xinput/form/{order_id}/{step}/submit', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{data}}),
  }});
  const result = await resp.json();
  alert(result.message || JSON.stringify(result));
  if (resp.ok) location.reload();
}});
</script>
</body></html>"""

    return HTMLResponse(content=html)


# ── POST /form/{order_id}/{step}/submit — accept submission ──


@router.post("/form/{order_id}/{step}/submit")
async def submit_form(order_id: str, step: int, body: FormSubmission, db: Session = Depends(get_db)):
    """Accept form data for a given step and mark it as submitted."""
    db_order = db.query(BecknOrder).filter_by(order_id=order_id).first()
    if not db_order:
        raise HTTPException(404, "Order not found")

    form_row = (
        db.query(XInputForm)
        .filter_by(order_id=order_id, step_index=step)
        .first()
    )
    if not form_row:
        raise HTTPException(404, f"Form step {step} not found")

    if form_row.submitted:
        raise HTTPException(409, f"Step {step} already submitted")

    # Save data
    form_row.form_data = body.data
    form_row.submitted = 1
    db.commit()

    # Update order xinput_submitted count
    submitted_count = (
        db.query(XInputForm)
        .filter_by(order_id=order_id, submitted=1)
        .count()
    )
    db_order.xinput_submitted = submitted_count

    # If all forms submitted, advance fulfillment status
    if submitted_count >= db_order.xinput_required:
        from app.db.models import FulfillmentStatusCode
        db_order.fulfillment_status = FulfillmentStatusCode.APPLICATION_FILLED

    db.commit()

    log.info(
        "XINPUT_SUBMIT order=%s step=%d submitted=%d/%d",
        order_id, step, submitted_count, db_order.xinput_required,
    )

    return {
        "message": f"Step {step} submitted successfully",
        "order_id": order_id,
        "step": step,
        "total_submitted": submitted_count,
        "total_required": db_order.xinput_required,
    }


# ── GET /status/{order_id} — check form completion ──


@router.get("/status/{order_id}", response_model=OrderFormStatus)
async def form_status(order_id: str, db: Session = Depends(get_db)):
    """Return the completion status of all xInput form steps for an order."""
    db_order = db.query(BecknOrder).filter_by(order_id=order_id).first()
    if not db_order:
        raise HTTPException(404, "Order not found")

    forms = (
        db.query(XInputForm)
        .filter_by(order_id=order_id)
        .order_by(XInputForm.step_index)
        .all()
    )

    steps = [
        FormStatusOut(
            form_id=f.form_id,
            step_index=f.step_index,
            heading=f.heading,
            submitted=bool(f.submitted),
            form_data=f.form_data,
        )
        for f in forms
    ]

    return OrderFormStatus(
        order_id=order_id,
        total_steps=db_order.xinput_required,
        submitted_steps=db_order.xinput_submitted,
        steps=steps,
    )
