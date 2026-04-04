"""
ONEST Registry Subscribe / on_subscribe Endpoints
===================================================

Implements the BPP ↔ Registry handshake:

1. BPP calls ``POST /subscribe`` on the registry with its subscriber info
   (including ed25519 public key).
2. Registry responds with ``/on_subscribe`` containing a challenge string
   signed with the registry's key.
3. BPP verifies and responds with the signed challenge (simplified here).

In this mock implementation we host both sides locally for testing:
    POST /api/registry/subscribe      – BPP → Registry
    POST /api/registry/on_subscribe   – Registry → BPP callback
    GET  /api/registry/lookup/{subscriber_id}  – simple lookup (mock)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.beckn_schemas import (
    BecknAckResponse,
    SubscribeRequest,
    OnSubscribeRequest,
    ack_response,
    nack_response,
)
from app.services.auth import get_public_key_b64, register_subscriber_key

log = logging.getLogger(__name__)

router = APIRouter(prefix="/registry", tags=["beckn-registry"])

# ── In-memory subscriber store (mock registry) ──
_subscribers: dict[str, dict] = {}


class SubscriberOut(BaseModel):
    subscriber_id: str
    type: str
    domain: str
    status: str
    cb_url: str
    signing_public_key: str


# ── POST /subscribe — BPP subscribes to registry ──


@router.post("/subscribe", response_model=BecknAckResponse)
async def registry_subscribe(body: SubscribeRequest):
    """
    Mock registry ``/subscribe`` endpoint.

    Accepts a subscriber registration and stores it. In production this
    would be hosted by the ONEST registry, not the BPP itself.
    """
    if not body.message:
        return nack_response("50001", "Missing subscriber info in message")

    info = body.message
    sub_id = info.subscriber_id

    _subscribers[sub_id] = {
        "subscriber_id": sub_id,
        "type": info.type,
        "cb_url": info.cb_url,
        "domain": info.domain,
        "city": info.city,
        "country": info.country,
        "signing_public_key": info.signing_public_key,
        "encryption_public_key": info.encryption_public_key,
        "status": "SUBSCRIBED",
        "created": datetime.now(timezone.utc).isoformat(),
        "updated": datetime.now(timezone.utc).isoformat(),
    }

    # Register the public key for auth verification
    register_subscriber_key(sub_id, info.signing_public_key)

    log.info("REGISTRY_SUBSCRIBE subscriber_id=%s type=%s", sub_id, info.type)

    return ack_response()


# ── POST /on_subscribe — registry callback to BPP ──


@router.post("/on_subscribe", response_model=BecknAckResponse)
async def registry_on_subscribe(body: OnSubscribeRequest):
    """
    Mock ``/on_subscribe`` callback.

    In production the registry sends this to the BPP's callback URL after
    verifying the subscription. Contains a challenge the BPP must sign.
    """
    sub_id = body.subscriber_id
    challenge = body.challenge

    log.info("REGISTRY_ON_SUBSCRIBE subscriber_id=%s challenge=%s", sub_id, challenge)

    if sub_id in _subscribers:
        _subscribers[sub_id]["status"] = "SUBSCRIBED"
        _subscribers[sub_id]["updated"] = datetime.now(timezone.utc).isoformat()

    return ack_response()


# ── GET /lookup/{subscriber_id} — mock lookup ──


@router.get("/lookup/{subscriber_id}", response_model=SubscriberOut | dict)
async def registry_lookup(subscriber_id: str):
    """Look up a subscriber in the mock registry."""
    sub = _subscribers.get(subscriber_id)
    if not sub:
        return {"error": f"Subscriber {subscriber_id} not found"}

    return SubscriberOut(
        subscriber_id=sub["subscriber_id"],
        type=sub["type"],
        domain=sub["domain"],
        status=sub["status"],
        cb_url=sub["cb_url"],
        signing_public_key=sub["signing_public_key"],
    )


# ── Convenience: self-register this BPP ──


def self_register(bpp_id: str, bpp_uri: str, domain: str = "onest:work-opportunities"):
    """
    Utility function called at startup to register *this* BPP in the
    mock registry so that auth verification works for self-sent callbacks.
    """
    pub_key = get_public_key_b64()

    _subscribers[bpp_id] = {
        "subscriber_id": bpp_id,
        "type": "bpp",
        "cb_url": bpp_uri,
        "domain": domain,
        "city": "*",
        "country": "IND",
        "signing_public_key": pub_key,
        "encryption_public_key": pub_key,  # same key for mock
        "status": "SUBSCRIBED",
        "created": datetime.now(timezone.utc).isoformat(),
        "updated": datetime.now(timezone.utc).isoformat(),
    }

    register_subscriber_key(bpp_id, pub_key)
    log.info("Self-registered BPP %s in mock registry", bpp_id)
