"""
Mock Beckn Gateway — receives and logs *all* Beckn ``on_*`` callbacks.

In a real ONEST deployment these callback endpoints would be part of the BAP.
Here we host them locally so the BPP can POST real Beckn-shaped payloads and
get a proper ACK back during development & testing.

Supported callbacks:
    POST /api/beckn/on_search
    POST /api/beckn/on_select
    POST /api/beckn/on_init
    POST /api/beckn/on_confirm
    POST /api/beckn/on_status
    POST /api/beckn/on_update
    POST /api/beckn/on_cancel

Debug:
    GET  /api/beckn/logs
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request

from app.api.beckn_schemas import (
    BecknAckResponse,
    OnSearchRequest,
    OnSelectRequest,
    OnInitRequest,
    OnConfirmRequest,
    OnStatusRequest,
    OnUpdateRequest,
    OnCancelRequest,
    ack_response,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/beckn", tags=["beckn-gateway"])

# In-memory ring buffer of the last 100 payloads received
_payload_log: deque[dict[str, Any]] = deque(maxlen=100)


def _store(action: str, payload: dict) -> None:
    _payload_log.append(
        {
            "received_at": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "payload": payload,
        }
    )


# ── Generic helper ────────────────────────────

def _log_and_ack(action: str, body, extra: str = "") -> BecknAckResponse:
    ctx = body.context
    log.info(
        "GATEWAY_%s | txn=%s | msg=%s %s",
        action.upper(),
        ctx.transaction_id,
        ctx.message_id,
        extra,
    )
    _store(action, body.model_dump(mode="json", exclude_none=True, by_alias=True))
    return ack_response()


# ── POST /on_search ──────────────────────────


@router.post("/on_search", response_model=BecknAckResponse)
async def beckn_on_search(body: OnSearchRequest):
    providers = body.message.catalog.providers
    item_count = sum(len(p.items or []) for p in providers)
    return _log_and_ack("on_search", body, f"| providers={len(providers)} items={item_count}")


# ── POST /on_select ──────────────────────────


@router.post("/on_select", response_model=BecknAckResponse)
async def beckn_on_select(body: OnSelectRequest):
    order = body.message.order
    return _log_and_ack("on_select", body, f"| order={order.id} state={order.state}")


# ── POST /on_init ────────────────────────────


@router.post("/on_init", response_model=BecknAckResponse)
async def beckn_on_init(body: OnInitRequest):
    order = body.message.order
    return _log_and_ack("on_init", body, f"| order={order.id} state={order.state}")


# ── POST /on_confirm ─────────────────────────


@router.post("/on_confirm", response_model=BecknAckResponse)
async def beckn_on_confirm(body: OnConfirmRequest):
    order = body.message.order
    return _log_and_ack("on_confirm", body, f"| order={order.id} state={order.state}")


# ── POST /on_status ──────────────────────────


@router.post("/on_status", response_model=BecknAckResponse)
async def beckn_on_status(body: OnStatusRequest):
    order = body.message.order
    return _log_and_ack("on_status", body, f"| order={order.id} state={order.state}")


# ── POST /on_update ──────────────────────────


@router.post("/on_update", response_model=BecknAckResponse)
async def beckn_on_update(body: OnUpdateRequest):
    order = body.message.order
    return _log_and_ack("on_update", body, f"| order={order.id} state={order.state}")


# ── POST /on_cancel ──────────────────────────


@router.post("/on_cancel", response_model=BecknAckResponse)
async def beckn_on_cancel(body: OnCancelRequest):
    order = body.message.order
    return _log_and_ack("on_cancel", body, f"| order={order.id} state={order.state}")


# ── GET /logs — debug helper ─────────────────


@router.get("/logs")
async def beckn_logs(limit: int = 20):
    """Return the most recent Beckn payloads received by this mock gateway."""
    entries = list(_payload_log)[-limit:]
    return {"count": len(entries), "entries": entries}
