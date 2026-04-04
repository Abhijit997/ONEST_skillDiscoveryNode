"""
Async callback poster — sends ``on_*`` responses back to the BAP callback URI.

In a real deployment this would use ``httpx.AsyncClient`` with retries and
ed25519 header signing.  For now we use a background task with ``requests``.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

log = logging.getLogger(__name__)

# How long to wait for BAP to respond (seconds)
CALLBACK_TIMEOUT = 5


def post_callback(bap_uri: str, action: str, payload: dict[str, Any]) -> bool:
    """
    POST *payload* to ``{bap_uri}/{action}`` (e.g. ``/on_select``).

    Returns True on a successful ACK response, False otherwise.
    """
    url = bap_uri.rstrip("/") + f"/{action}"
    log.info("CALLBACK → %s  txn=%s", url, payload.get("context", {}).get("transaction_id"))

    try:
        resp = requests.post(url, json=payload, timeout=CALLBACK_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
        ack = body.get("message", {}).get("ack", {}).get("status", "")
        if ack == "ACK":
            log.info("CALLBACK ACK from %s", url)
            return True
        log.warning("CALLBACK NACK from %s: %s", url, body)
        return False
    except requests.RequestException as exc:
        log.warning("CALLBACK FAILED to %s: %s", url, exc)
        return False
