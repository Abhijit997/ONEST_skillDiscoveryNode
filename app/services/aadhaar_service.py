"""
Mock DigiLocker Aadhaar verification service.

In production, swap MockDigiLockerService → RealDigiLockerService that calls
the actual DigiLocker Partner API (https://partners.digitallocker.gov.in).

The interface stays the same so the chat flow & API layer don't change.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class DigiLockerAuthResult:
    """Returned by initiate() — mock authorization URL + transaction id."""
    transaction_id: str
    auth_url: str
    masked_aadhaar: str  # e.g. "XXXX-XXXX-1234"


@dataclass
class DigiLockerKYC:
    """e-KYC data returned after successful verification."""
    transaction_id: str
    verified: bool
    name: str
    dob: str | None  # ISO date string
    gender: str | None
    district: str | None
    state: str | None
    pincode: str | None
    photo_base64: str | None = None  # placeholder


class MockDigiLockerService:
    """
    Simulates the DigiLocker OAuth + e-KYC flow.

    initiate()       → returns a mock auth URL + transaction id
    complete()       → simulates the callback (worker tapped "Allow")
    fetch_ekyc()     → returns the worker's own data as mock UIDAI e-KYC
    """

    # In-memory store of pending transactions (lost on restart — fine for mock)
    _pending: dict[str, dict] = {}

    @classmethod
    def initiate(cls, worker_id: str, aadhar_hash: str) -> DigiLockerAuthResult:
        """Step 1: Generate mock DigiLocker authorization URL."""
        txn_id = f"TXN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        masked = f"XXXX-XXXX-{aadhar_hash[-4:]}"

        cls._pending[txn_id] = {
            "worker_id": worker_id,
            "aadhar_hash": aadhar_hash,
            "created": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }

        # In production this would be:
        # https://digilocker.meripehchaan.gov.in/public/oauth2/1/authorize?...
        auth_url = (
            f"https://digilocker.meripehchaan.gov.in/public/oauth2/1/authorize"
            f"?client_id=MOCK_CLIENT_ID"
            f"&redirect_uri=http://localhost:8000/api/aadhaar/callback"
            f"&response_type=code"
            f"&state={txn_id}"
        )

        return DigiLockerAuthResult(
            transaction_id=txn_id,
            auth_url=auth_url,
            masked_aadhaar=masked,
        )

    @classmethod
    def complete(cls, transaction_id: str) -> bool:
        """Step 2: Simulate the worker clicking 'Allow' on DigiLocker."""
        if transaction_id not in cls._pending:
            return False
        cls._pending[transaction_id]["status"] = "authorized"
        return True

    @classmethod
    def fetch_ekyc(
        cls,
        transaction_id: str,
        *,
        # Worker data from our DB — returned as if DigiLocker sent it
        name: str,
        dob: str | None = None,
        district: str | None = None,
    ) -> DigiLockerKYC | None:
        """Step 3: Exchange auth code → fetch e-KYC data (mocked)."""
        txn = cls._pending.get(transaction_id)
        if not txn or txn["status"] != "authorized":
            return None

        txn["status"] = "completed"

        return DigiLockerKYC(
            transaction_id=transaction_id,
            verified=True,
            name=name,
            dob=dob,
            gender=None,        # could add to worker_stage later
            district=district,
            state=None,         # could add to worker_stage later
            pincode=None,       # could add to worker_stage later
            photo_base64=None,  # placeholder
        )
