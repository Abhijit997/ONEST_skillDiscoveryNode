"""
BPP (Beckn Provider Platform) Endpoints
========================================

Implements the **full** ONEST / Beckn BPP action set for the
``onest:work-opportunities`` domain.

Incoming actions (BAP → BPP):
    POST /bpp/search   — catalog search
    POST /bpp/select   — select a job listing
    POST /bpp/init     — initialise an application (may include xInput)
    POST /bpp/confirm  — confirm the application
    POST /bpp/status   — query application status
    POST /bpp/update   — update an existing order
    POST /bpp/cancel   — cancel an application

Each endpoint returns an immediate Beckn ACK and schedules an async
background task that builds the ``on_*`` callback payload and POSTs it
back to the BAP's callback URI (``context.bap_uri``).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api.beckn_schemas import (
    BecknAckResponse,
    Billing,
    Catalog,
    Context,
    Customer,
    Descriptor,
    Fulfillment,
    FulfillmentState,
    Item,
    Location,
    City,
    State,
    OnSearchMessage,
    OnSearchRequest,
    Order,
    Person,
    Provider,
    SearchRequest,
    SelectRequest,
    InitRequest,
    ConfirmRequest,
    StatusRequest,
    UpdateRequest,
    CancelRequest,
    Tag,
    TagDescriptor,
    TagListItem,
    XInput,
    XInputForm as XInputFormSchema,
    XInputFormHead,
    ack_response,
    nack_response,
)
from app.db.database import get_db
from app.db.models import (
    BecknOrder,
    FulfillmentStatusCode,
    FulfillmentType,
    OrderState,
    WorkerStage,
    XInputForm as XInputFormModel,
)
from app.services.beckn_callback import post_callback

log = logging.getLogger(__name__)

router = APIRouter(prefix="/bpp", tags=["beckn-bpp"])

# ── Constants ─────────────────────────────────

BPP_ID = "onest-skill-discovery.bpp.io"
BPP_URI = "https://onest-skill-discovery.bpp.io"
XINPUT_BASE_URL = "http://127.0.0.1:8000/api/xinput"  # form URL prefix

# Number of xInput form steps an applicant must complete
XINPUT_TOTAL_STEPS = 2
XINPUT_HEADINGS = ["Personal Details", "Upload Documents"]


# ── Helpers ───────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_callback_context(incoming: Context, action: str) -> dict:
    """Clone incoming context, flip action to on_*, regenerate message_id."""
    return Context(
        domain=incoming.domain,
        action=action,
        version=incoming.version,
        bap_id=incoming.bap_id,
        bap_uri=incoming.bap_uri,
        bpp_id=BPP_ID,
        bpp_uri=BPP_URI,
        transaction_id=incoming.transaction_id,
        message_id=str(uuid.uuid4()),
        timestamp=_now_iso(),
        ttl=incoming.ttl,
    ).model_dump(mode="json", exclude_none=True)


def _worker_to_item(w: WorkerStage) -> dict:
    """Convert a WorkerStage row to a Beckn Item dict."""
    tags = []

    # listing-details tag group
    listing_items = [
        TagListItem(
            descriptor=TagDescriptor(code="industry-type", name="Industry type"),
            value="Blue Collar Services",
        ),
        TagListItem(
            descriptor=TagDescriptor(code="employment-type", name="Employment type"),
            value="full-time",
        ),
        TagListItem(
            descriptor=TagDescriptor(code="job-role", name="Job role"),
            value=w.skill_category.value if hasattr(w.skill_category, "value") else str(w.skill_category),
        ),
    ]
    tags.append(
        Tag(
            display=True,
            descriptor=TagDescriptor(code="listing-details", name="Listing details"),
            items=listing_items,
        )
    )

    # salary-info (mock values — replace with real data later)
    tags.append(
        Tag(
            display=True,
            descriptor=TagDescriptor(code="salary-info", name="Salary information"),
            items=[
                TagListItem(
                    descriptor=TagDescriptor(code="gross-min", name="Minimum gross"),
                    value="180000",
                ),
                TagListItem(
                    descriptor=TagDescriptor(code="gross-max", name="Maximum gross"),
                    value="360000",
                ),
            ],
        )
    )

    item = Item(
        id=w.worker_id,
        descriptor=Descriptor(
            name=f"{w.skill_category.value if hasattr(w.skill_category, 'value') else w.skill_category} — {w.name}",
            short_desc=f"Verified worker in {w.district}",
        ),
        location_ids=["L1"],
        fulfillment_ids=["1"],
        tags=tags,
    )
    return item.model_dump(mode="json", exclude_none=True, by_alias=True)


def _build_order_payload(order: BecknOrder, worker: WorkerStage | None = None) -> dict:
    """Build a Beckn Order dict from a DB order row."""
    fulfillment_state = FulfillmentState(
        descriptor=Descriptor(
            name=order.fulfillment_status.value
            if hasattr(order.fulfillment_status, "value")
            else str(order.fulfillment_status),
            code=order.fulfillment_status.value
            if hasattr(order.fulfillment_status, "value")
            else str(order.fulfillment_status),
        ),
        updated_at=order.updated_ts.isoformat() if order.updated_ts else _now_iso(),
    )

    fulfillment = Fulfillment(
        id="1",
        type=order.fulfillment_type.value if hasattr(order.fulfillment_type, "value") else str(order.fulfillment_type),
        state=fulfillment_state,
        customer=Customer(
            person=Person(**(order.customer_person or {})) if order.customer_person else None,
            contact=None,
        ) if order.customer_person else None,
    )

    # Build xInput for the order
    xinput = None
    if order.xinput_required and order.xinput_submitted < order.xinput_required:
        cur_step = order.xinput_submitted
        xinput = XInput(
            required=True,
            head=XInputFormHead(
                descriptor=Descriptor(name="Application Form"),
                index={"min": 0, "cur": cur_step, "max": order.xinput_required - 1},
                headings=XINPUT_HEADINGS[: order.xinput_required],
            ),
            form=XInputFormSchema(
                mime_type="text/html",
                url=f"{XINPUT_BASE_URL}/form/{order.order_id}/{cur_step}",
            ),
        )

    items = []
    if order.item_id:
        item = Item(
            id=order.item_id,
            descriptor=Descriptor(name=order.item_id),
            xinput=xinput,
        )
        items.append(item)

    billing = None
    if order.billing:
        billing = Billing(**(order.billing))

    o = Order(
        id=order.order_id,
        state=order.state.value if hasattr(order.state, "value") else str(order.state),
        provider=Provider(
            id=order.provider_id or BPP_ID,
            descriptor=Descriptor(name="ONEST Skill Discovery Node"),
        ),
        items=items,
        fulfillments=[fulfillment],
        billing=billing,
        created_at=order.created_ts.isoformat() if order.created_ts else None,
        updated_at=order.updated_ts.isoformat() if order.updated_ts else None,
    )
    return o.model_dump(mode="json", exclude_none=True, by_alias=True)


# ═══════════════════════════════════════════════
#  POST /bpp/search
# ═══════════════════════════════════════════════


def _handle_search(context_dict: dict, body: SearchRequest, db: Session):
    """Background: build on_search catalog and POST to BAP."""
    workers = db.query(WorkerStage).filter(
        WorkerStage.status.in_(["active", "verified"]),
        WorkerStage.availability_status.in_(["available", "partially_available"]),
    ).limit(50).all()

    # Apply intent filters if present
    intent = body.message.intent
    if intent and intent.descriptor and intent.descriptor.name:
        query_lower = intent.descriptor.name.lower()
        workers = [w for w in workers if query_lower in (w.name or "").lower()
                   or query_lower in (w.skill_category.value if hasattr(w.skill_category, "value") else str(w.skill_category)).lower()]

    items_data = [_worker_to_item(w) for w in workers]

    # Build location from first worker or default
    location_data = {
        "id": "L1",
        "city": {"name": workers[0].district if workers else "India"},
    }

    fulfillment_data = {"id": "1", "type": "ONSITE"}

    payload = {
        "context": _make_callback_context(body.context, "on_search"),
        "message": {
            "catalog": {
                "descriptor": {"name": "ONEST Skill Discovery Catalog"},
                "providers": [
                    {
                        "id": BPP_ID,
                        "descriptor": {
                            "name": "ONEST Skill Discovery Node",
                            "short_desc": "Blue-collar worker discovery platform",
                        },
                        "locations": [location_data],
                        "fulfillments": [fulfillment_data],
                        "items": items_data,
                    }
                ],
            }
        },
    }

    bap_uri = body.context.bap_uri or "http://127.0.0.1:8000/api/beckn"
    post_callback(bap_uri, "on_search", payload)


@router.post("/search", response_model=BecknAckResponse)
async def bpp_search(body: SearchRequest, bg: BackgroundTasks, db: Session = Depends(get_db)):
    """BAP → BPP search. Returns ACK, posts on_search async."""
    log.info("BPP_SEARCH txn=%s", body.context.transaction_id)
    ctx = _make_callback_context(body.context, "on_search")
    bg.add_task(_handle_search, ctx, body, db)
    return ack_response()


# ═══════════════════════════════════════════════
#  POST /bpp/select
# ═══════════════════════════════════════════════


def _handle_select(body: SelectRequest, db: Session):
    """Background: create a DRAFT order and POST on_select."""
    order_msg = body.message.order
    item_id = order_msg.items[0].id if order_msg.items else None
    provider_id = order_msg.provider.id if order_msg.provider else BPP_ID

    # Create draft order
    db_order = BecknOrder(
        transaction_id=body.context.transaction_id,
        message_id=body.context.message_id,
        bap_id=body.context.bap_id or "",
        bap_uri=body.context.bap_uri or "",
        item_id=item_id,
        provider_id=provider_id,
        worker_id=item_id,  # item_id == worker_id in our model
        state=OrderState.DRAFT,
        fulfillment_status=FulfillmentStatusCode.APPLICATION_STARTED,
        fulfillment_type=FulfillmentType.ONSITE,
        xinput_required=XINPUT_TOTAL_STEPS,
        xinput_submitted=0,
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    # Create xInput form stubs
    for i in range(XINPUT_TOTAL_STEPS):
        form = XInputFormModel(
            order_id=db_order.order_id,
            transaction_id=body.context.transaction_id,
            step_index=i,
            heading=XINPUT_HEADINGS[i] if i < len(XINPUT_HEADINGS) else f"Step {i}",
        )
        db.add(form)
    db.commit()

    order_payload = _build_order_payload(db_order)

    payload = {
        "context": _make_callback_context(body.context, "on_select"),
        "message": {"order": order_payload},
    }

    bap_uri = body.context.bap_uri or "http://127.0.0.1:8000/api/beckn"
    post_callback(bap_uri, "on_select", payload)


@router.post("/select", response_model=BecknAckResponse)
async def bpp_select(body: SelectRequest, bg: BackgroundTasks, db: Session = Depends(get_db)):
    """BAP → BPP select. Returns ACK, creates draft order, posts on_select."""
    log.info("BPP_SELECT txn=%s", body.context.transaction_id)

    # Check item exists
    if body.message.order.items:
        item_id = body.message.order.items[0].id
        worker = db.query(WorkerStage).filter_by(worker_id=item_id).first()
        if not worker:
            return nack_response("30004", f"Item {item_id} not found")

    bg.add_task(_handle_select, body, db)
    return ack_response()


# ═══════════════════════════════════════════════
#  POST /bpp/init
# ═══════════════════════════════════════════════


def _handle_init(body: InitRequest, db: Session):
    """Background: populate customer/billing on order, POST on_init."""
    txn_id = body.context.transaction_id
    db_order = db.query(BecknOrder).filter_by(transaction_id=txn_id).first()
    if not db_order:
        log.warning("INIT: order not found for txn=%s", txn_id)
        return

    order_msg = body.message.order

    # Store customer info
    if order_msg.fulfillments:
        ff = order_msg.fulfillments[0]
        if ff.customer:
            if ff.customer.person:
                db_order.customer_person = ff.customer.person.model_dump(mode="json", exclude_none=True)
            if ff.customer.contact:
                db_order.customer_contact = ff.customer.contact.model_dump(mode="json", exclude_none=True)

    # Store billing
    if order_msg.billing:
        db_order.billing = order_msg.billing.model_dump(mode="json", exclude_none=True)

    db_order.fulfillment_status = FulfillmentStatusCode.APPLICATION_STARTED
    db.commit()
    db.refresh(db_order)

    order_payload = _build_order_payload(db_order)

    payload = {
        "context": _make_callback_context(body.context, "on_init"),
        "message": {"order": order_payload},
    }

    bap_uri = body.context.bap_uri or "http://127.0.0.1:8000/api/beckn"
    post_callback(bap_uri, "on_init", payload)


@router.post("/init", response_model=BecknAckResponse)
async def bpp_init(body: InitRequest, bg: BackgroundTasks, db: Session = Depends(get_db)):
    """BAP → BPP init. Returns ACK, posts on_init with xInput forms."""
    log.info("BPP_INIT txn=%s", body.context.transaction_id)
    txn_id = body.context.transaction_id
    db_order = db.query(BecknOrder).filter_by(transaction_id=txn_id).first()
    if not db_order:
        return nack_response("40002", "Order not found for this transaction")

    bg.add_task(_handle_init, body, db)
    return ack_response()


# ═══════════════════════════════════════════════
#  POST /bpp/confirm
# ═══════════════════════════════════════════════


def _handle_confirm(body: ConfirmRequest, db: Session):
    """Background: activate order and POST on_confirm."""
    txn_id = body.context.transaction_id
    db_order = db.query(BecknOrder).filter_by(transaction_id=txn_id).first()
    if not db_order:
        log.warning("CONFIRM: order not found for txn=%s", txn_id)
        return

    # Check all xInput forms are submitted
    if db_order.xinput_required > 0 and db_order.xinput_submitted < db_order.xinput_required:
        log.warning(
            "CONFIRM: xInput incomplete for txn=%s (%d/%d)",
            txn_id, db_order.xinput_submitted, db_order.xinput_required,
        )
        # Still proceed but keep APPLICATION_FILLED status

    db_order.state = OrderState.ACTIVE
    db_order.fulfillment_status = FulfillmentStatusCode.APPLICATION_FILLED
    db.commit()
    db.refresh(db_order)

    order_payload = _build_order_payload(db_order)

    payload = {
        "context": _make_callback_context(body.context, "on_confirm"),
        "message": {"order": order_payload},
    }

    bap_uri = body.context.bap_uri or "http://127.0.0.1:8000/api/beckn"
    post_callback(bap_uri, "on_confirm", payload)


@router.post("/confirm", response_model=BecknAckResponse)
async def bpp_confirm(body: ConfirmRequest, bg: BackgroundTasks, db: Session = Depends(get_db)):
    """BAP → BPP confirm. Returns ACK, activates order, posts on_confirm."""
    log.info("BPP_CONFIRM txn=%s", body.context.transaction_id)
    txn_id = body.context.transaction_id
    db_order = db.query(BecknOrder).filter_by(transaction_id=txn_id).first()
    if not db_order:
        return nack_response("40002", "Order not found for this transaction")

    bg.add_task(_handle_confirm, body, db)
    return ack_response()


# ═══════════════════════════════════════════════
#  POST /bpp/status
# ═══════════════════════════════════════════════


def _handle_status(body: StatusRequest, db: Session):
    """Background: return current order state via on_status."""
    txn_id = body.context.transaction_id

    # Allow lookup by order_id passed in message.order.id
    order_id = body.message.order.id if body.message.order.id else None
    if order_id:
        db_order = db.query(BecknOrder).filter_by(order_id=order_id).first()
    else:
        db_order = db.query(BecknOrder).filter_by(transaction_id=txn_id).first()

    if not db_order:
        log.warning("STATUS: order not found for txn=%s", txn_id)
        return

    order_payload = _build_order_payload(db_order)

    payload = {
        "context": _make_callback_context(body.context, "on_status"),
        "message": {"order": order_payload},
    }

    bap_uri = body.context.bap_uri or "http://127.0.0.1:8000/api/beckn"
    post_callback(bap_uri, "on_status", payload)


@router.post("/status", response_model=BecknAckResponse)
async def bpp_status(body: StatusRequest, bg: BackgroundTasks, db: Session = Depends(get_db)):
    """BAP → BPP status. Returns ACK, posts on_status with current order state."""
    log.info("BPP_STATUS txn=%s", body.context.transaction_id)
    bg.add_task(_handle_status, body, db)
    return ack_response()


# ═══════════════════════════════════════════════
#  POST /bpp/update
# ═══════════════════════════════════════════════


def _handle_update(body: UpdateRequest, db: Session):
    """Background: update order and POST on_update."""
    txn_id = body.context.transaction_id
    order_msg = body.message.order

    order_id = order_msg.id
    if order_id:
        db_order = db.query(BecknOrder).filter_by(order_id=order_id).first()
    else:
        db_order = db.query(BecknOrder).filter_by(transaction_id=txn_id).first()

    if not db_order:
        log.warning("UPDATE: order not found for txn=%s", txn_id)
        return

    if db_order.state in (OrderState.CANCELLED, OrderState.COMPLETE):
        log.warning("UPDATE: cannot update order in state %s", db_order.state)
        return

    # Apply updates — customer, billing, fulfillment
    if order_msg.fulfillments:
        ff = order_msg.fulfillments[0]
        if ff.customer and ff.customer.person:
            db_order.customer_person = ff.customer.person.model_dump(mode="json", exclude_none=True)
        if ff.type:
            try:
                db_order.fulfillment_type = FulfillmentType(ff.type)
            except ValueError:
                pass

    if order_msg.billing:
        db_order.billing = order_msg.billing.model_dump(mode="json", exclude_none=True)

    db.commit()
    db.refresh(db_order)

    order_payload = _build_order_payload(db_order)

    payload = {
        "context": _make_callback_context(body.context, "on_update"),
        "message": {"order": order_payload},
    }

    bap_uri = body.context.bap_uri or "http://127.0.0.1:8000/api/beckn"
    post_callback(bap_uri, "on_update", payload)


@router.post("/update", response_model=BecknAckResponse)
async def bpp_update(body: UpdateRequest, bg: BackgroundTasks, db: Session = Depends(get_db)):
    """BAP → BPP update. Returns ACK, applies updates, posts on_update."""
    log.info("BPP_UPDATE txn=%s", body.context.transaction_id)
    bg.add_task(_handle_update, body, db)
    return ack_response()


# ═══════════════════════════════════════════════
#  POST /bpp/cancel
# ═══════════════════════════════════════════════


def _handle_cancel(body: CancelRequest, db: Session):
    """Background: cancel order and POST on_cancel."""
    txn_id = body.context.transaction_id
    order_msg = body.message.order

    order_id = order_msg.id
    if order_id:
        db_order = db.query(BecknOrder).filter_by(order_id=order_id).first()
    else:
        db_order = db.query(BecknOrder).filter_by(transaction_id=txn_id).first()

    if not db_order:
        log.warning("CANCEL: order not found for txn=%s", txn_id)
        return

    if db_order.state == OrderState.CANCELLED:
        log.warning("CANCEL: order already cancelled txn=%s", txn_id)
        return

    # Record cancellation
    db_order.state = OrderState.CANCELLED
    db_order.fulfillment_status = FulfillmentStatusCode.CANCELLED
    if order_msg.cancellation and order_msg.cancellation.reason:
        db_order.cancellation_reason = order_msg.cancellation.reason.name or order_msg.cancellation.reason.code
    else:
        db_order.cancellation_reason = "Cancelled by BAP"

    db.commit()
    db.refresh(db_order)

    order_payload = _build_order_payload(db_order)
    if order_msg.cancellation:
        order_payload["cancellation"] = order_msg.cancellation.model_dump(mode="json", exclude_none=True)

    payload = {
        "context": _make_callback_context(body.context, "on_cancel"),
        "message": {"order": order_payload},
    }

    bap_uri = body.context.bap_uri or "http://127.0.0.1:8000/api/beckn"
    post_callback(bap_uri, "on_cancel", payload)


@router.post("/cancel", response_model=BecknAckResponse)
async def bpp_cancel(body: CancelRequest, bg: BackgroundTasks, db: Session = Depends(get_db)):
    """BAP → BPP cancel. Returns ACK, cancels order, posts on_cancel."""
    log.info("BPP_CANCEL txn=%s", body.context.transaction_id)
    bg.add_task(_handle_cancel, body, db)
    return ack_response()
