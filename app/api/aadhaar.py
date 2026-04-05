"""
Aadhaar verification API routes (mock DigiLocker flow).

POST /api/aadhaar/initiate          — start mock DigiLocker auth
POST /api/aadhaar/callback          — simulate worker clicking "Allow"
POST /api/aadhaar/fetch-document    — exchange code → get mock e-KYC
GET  /api/aadhaar/status/{wid}      — current Aadhaar verification status

In production, swap MockDigiLockerService → RealDigiLockerService.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from datetime import datetime, timezone

from app.db.database import get_db
from app.db.models import Worker
from app.services.aadhaar_service import MockDigiLockerService


router = APIRouter(prefix="/aadhaar", tags=["aadhaar"])


# ── Schemas ──


class InitiateRequest(BaseModel):
    worker_id: str


class InitiateResponse(BaseModel):
    transaction_id: str
    auth_url: str
    masked_aadhaar: str
    message: str


class CallbackRequest(BaseModel):
    transaction_id: str


class CallbackResponse(BaseModel):
    transaction_id: str
    authorized: bool


class FetchDocumentRequest(BaseModel):
    worker_id: str
    transaction_id: str


class EKYCData(BaseModel):
    name: str
    dob: str | None = None
    district: str | None = None
    gender: str | None = None
    state: str | None = None
    pincode: str | None = None


class FetchDocumentResponse(BaseModel):
    transaction_id: str
    verified: bool
    ekyc: EKYCData | None = None
    aadhaar_verified: bool = False
    message: str


class AadhaarStatusResponse(BaseModel):
    worker_id: str
    aadhaar_verified: bool
    transaction_id: str | None = None


# ── Helpers ──


def _get_worker_or_404(worker_id: str, db: Session) -> Worker:
    worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Worker not found")
    return worker


# ── Endpoints ──


@router.post(
    "/initiate",
    response_model=InitiateResponse,
    summary="Start Aadhaar verification via DigiLocker (mock)",
)
def initiate_verification(req: InitiateRequest, db: Session = Depends(get_db)):
    worker = _get_worker_or_404(req.worker_id, db)

    result = MockDigiLockerService.initiate(
        worker_id=worker.worker_id,
        aadhar_hash=worker.aadhar_hash,
    )

    return InitiateResponse(
        transaction_id=result.transaction_id,
        auth_url=result.auth_url,
        masked_aadhaar=result.masked_aadhaar,
        message=f"DigiLocker authorization link generated for Aadhaar {result.masked_aadhaar}",
    )


@router.post(
    "/callback",
    response_model=CallbackResponse,
    summary="Simulate DigiLocker callback (worker clicked 'Allow')",
)
def digilocker_callback(req: CallbackRequest):
    ok = MockDigiLockerService.complete(req.transaction_id)
    if not ok:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Transaction '{req.transaction_id}' not found or already completed.",
        )
    return CallbackResponse(transaction_id=req.transaction_id, authorized=True)


@router.post(
    "/fetch-document",
    response_model=FetchDocumentResponse,
    summary="Exchange auth code → fetch Aadhaar e-KYC data (mock)",
)
def fetch_document(req: FetchDocumentRequest, db: Session = Depends(get_db)):
    worker = _get_worker_or_404(req.worker_id, db)

    kyc = MockDigiLockerService.fetch_ekyc(
        transaction_id=req.transaction_id,
        name=worker.name,
        dob=worker.dob.isoformat() if worker.dob else None,
        district=worker.district,
    )

    if kyc is None:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Transaction not authorized or already used.",
        )

    # Update worker's verification_status
    verification = worker.verification_status or {}
    verification["aadhaar_verified"] = True
    verification["aadhaar_txn_id"] = kyc.transaction_id
    worker.verification_status = verification
    worker.updated_ts = datetime.now(timezone.utc)
    flag_modified(worker, "verification_status")
    db.commit()
    db.refresh(worker)

    ekyc_data = EKYCData(
        name=kyc.name,
        dob=kyc.dob,
        district=kyc.district,
        gender=kyc.gender,
        state=kyc.state,
        pincode=kyc.pincode,
    )

    return FetchDocumentResponse(
        transaction_id=kyc.transaction_id,
        verified=True,
        ekyc=ekyc_data,
        aadhaar_verified=True,
        message=f"Aadhaar verified for {kyc.name}",
    )


@router.get(
    "/status/{worker_id}",
    response_model=AadhaarStatusResponse,
    summary="Get Aadhaar verification status for a worker",
)
def aadhaar_status(worker_id: str, db: Session = Depends(get_db)):
    worker = _get_worker_or_404(worker_id, db)
    verification = worker.verification_status or {}

    return AadhaarStatusResponse(
        worker_id=worker_id,
        aadhaar_verified=bool(verification.get("aadhaar_verified", False)),
        transaction_id=verification.get("aadhaar_txn_id"),
    )
