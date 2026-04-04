"""
ed25519 Signing & Verification for Beckn Protocol
===================================================

Implements the Beckn authorization header scheme:

    Authorization: Signature keyId="{subscriber_id}|{unique_key_id}|ed25519",
                   algorithm="ed25519",
                   created="{unix_ts}",
                   expires="{unix_ts}",
                   headers="(created) (expires) digest",
                   signature="{base64_sig}"

    Digest: BLAKE-512={base64_hash}

Key management:
    - On first run, generates an ed25519 keypair and persists it to
      ``data/keys/`` as PEM files.
    - The public key (base64) is used when subscribing to the registry.
    - The private key signs every outgoing Beckn callback payload.
    - Incoming BAP requests are verified against the BAP's public key
      (looked up from an in-memory registry cache).

Dependencies:
    pip install PyNaCl
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

KEYS_DIR = Path("data/keys")

# ── In-memory store of known subscriber public keys ──
# subscriber_id -> base64-encoded ed25519 public key
_subscriber_keys: dict[str, str] = {}


def _ensure_keys_dir():
    KEYS_DIR.mkdir(parents=True, exist_ok=True)


# ── Key Generation ────────────────────────────


def generate_keypair() -> tuple[bytes, bytes]:
    """
    Generate an ed25519 keypair.
    Returns (private_key_bytes_32, public_key_bytes_32).
    """
    try:
        from nacl.signing import SigningKey
    except ImportError:
        log.warning("PyNaCl not installed — using fallback stub keys. Install with: pip install PyNaCl")
        # Return deterministic stub keys for dev mode
        stub_priv = b"\x00" * 32
        stub_pub = b"\x01" * 32
        return stub_priv, stub_pub

    sk = SigningKey.generate()
    return bytes(sk), bytes(sk.verify_key)


def load_or_create_keypair() -> tuple[bytes, bytes]:
    """Load keypair from disk, or generate + save a new one."""
    _ensure_keys_dir()
    priv_path = KEYS_DIR / "signing_private.key"
    pub_path = KEYS_DIR / "signing_public.key"

    if priv_path.exists() and pub_path.exists():
        priv = priv_path.read_bytes()
        pub = pub_path.read_bytes()
        log.info("Loaded ed25519 keypair from %s", KEYS_DIR)
        return priv, pub

    priv, pub = generate_keypair()
    priv_path.write_bytes(priv)
    pub_path.write_bytes(pub)
    log.info("Generated new ed25519 keypair at %s", KEYS_DIR)
    return priv, pub


# Module-level keypair (lazy init)
_private_key: bytes | None = None
_public_key: bytes | None = None


def get_keypair() -> tuple[bytes, bytes]:
    global _private_key, _public_key
    if _private_key is None:
        _private_key, _public_key = load_or_create_keypair()
    return _private_key, _public_key


def get_public_key_b64() -> str:
    """Return base64-encoded public key for registry subscription."""
    _, pub = get_keypair()
    return base64.b64encode(pub).decode()


# ── Signing ───────────────────────────────────


def _blake512_digest(body_bytes: bytes) -> str:
    """Compute BLAKE2b-512 digest and return as base64."""
    h = hashlib.blake2b(body_bytes, digest_size=64)
    return base64.b64encode(h.digest()).decode()


def sign_payload(payload: dict[str, Any], subscriber_id: str, unique_key_id: str = "key1") -> dict[str, str]:
    """
    Sign a Beckn payload and return headers dict with Authorization + Digest.

    Returns:
        {"Authorization": "Signature ...", "Digest": "BLAKE-512=..."}
    """
    body_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()

    digest_b64 = _blake512_digest(body_bytes)
    digest_header = f"BLAKE-512={digest_b64}"

    created = int(time.time())
    expires = created + 300  # 5 minutes

    signing_string = f"(created): {created}\n(expires): {expires}\ndigest: {digest_header}"

    priv, _ = get_keypair()

    try:
        from nacl.signing import SigningKey
        sk = SigningKey(priv)
        sig_bytes = sk.sign(signing_string.encode()).signature
    except ImportError:
        log.warning("PyNaCl not installed — using empty signature stub")
        sig_bytes = b"\x00" * 64

    sig_b64 = base64.b64encode(sig_bytes).decode()

    auth_header = (
        f'Signature keyId="{subscriber_id}|{unique_key_id}|ed25519",'
        f'algorithm="ed25519",'
        f'created="{created}",'
        f'expires="{expires}",'
        f'headers="(created) (expires) digest",'
        f'signature="{sig_b64}"'
    )

    return {"Authorization": auth_header, "Digest": digest_header}


# ── Verification ──────────────────────────────


def register_subscriber_key(subscriber_id: str, public_key_b64: str):
    """Cache a subscriber's public key for verification."""
    _subscriber_keys[subscriber_id] = public_key_b64
    log.info("Registered public key for subscriber %s", subscriber_id)


def verify_request(
    auth_header: str,
    digest_header: str,
    body_bytes: bytes,
) -> tuple[bool, str]:
    """
    Verify a Beckn Authorization header signature.

    Returns (is_valid, error_message).
    """
    import re

    # Parse Authorization header
    key_id_match = re.search(r'keyId="([^"]+)"', auth_header)
    created_match = re.search(r'created="(\d+)"', auth_header)
    expires_match = re.search(r'expires="(\d+)"', auth_header)
    sig_match = re.search(r'signature="([^"]+)"', auth_header)

    if not all([key_id_match, created_match, expires_match, sig_match]):
        return False, "Malformed Authorization header"

    key_id = key_id_match.group(1)
    created = int(created_match.group(1))
    expires = int(expires_match.group(1))
    sig_b64 = sig_match.group(1)

    # Check expiration
    now = int(time.time())
    if now > expires:
        return False, "Signature expired"

    # Parse keyId to get subscriber_id
    parts = key_id.split("|")
    if len(parts) < 3:
        return False, f"Invalid keyId format: {key_id}"

    subscriber_id = parts[0]

    # Look up public key
    pub_key_b64 = _subscriber_keys.get(subscriber_id)
    if not pub_key_b64:
        return False, f"Unknown subscriber: {subscriber_id}"

    # Verify digest
    expected_digest = f"BLAKE-512={_blake512_digest(body_bytes)}"
    if digest_header != expected_digest:
        return False, "Digest mismatch"

    # Reconstruct signing string
    signing_string = f"(created): {created}\n(expires): {expires}\ndigest: {digest_header}"

    try:
        from nacl.signing import VerifyKey
        pub_bytes = base64.b64decode(pub_key_b64)
        vk = VerifyKey(pub_bytes)
        sig_bytes = base64.b64decode(sig_b64)
        vk.verify(signing_string.encode(), sig_bytes)
        return True, ""
    except ImportError:
        log.warning("PyNaCl not installed — skipping signature verification")
        return True, ""
    except Exception as exc:
        return False, f"Signature verification failed: {exc}"


# ── FastAPI Middleware (optional) ─────────────


async def verify_beckn_auth_middleware(request, call_next):
    """
    Optional ASGI middleware that checks the Beckn Authorization header
    on incoming /bpp/* requests.

    Enable by adding to the FastAPI app:
        app.middleware("http")(verify_beckn_auth_middleware)
    """
    if request.url.path.startswith("/api/bpp/"):
        auth = request.headers.get("Authorization", "")
        digest = request.headers.get("Digest", "")

        if auth and digest:
            body = await request.body()
            valid, err = verify_request(auth, digest, body)
            if not valid:
                from fastapi.responses import JSONResponse
                log.warning("AUTH_FAILED path=%s error=%s", request.url.path, err)
                return JSONResponse(
                    status_code=401,
                    content={
                        "message": {"ack": {"status": "NACK"}},
                        "error": {"type": "CONTEXT-ERROR", "code": "10000", "message": err},
                    },
                )
        else:
            # In dev mode we skip auth if no headers present
            log.debug("No Beckn auth headers on %s — skipping verification", request.url.path)

    return await call_next(request)
