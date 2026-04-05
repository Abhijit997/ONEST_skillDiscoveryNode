"""
Chat API routes — phone-verification chat simulator.

Conversations are persisted in verification_status.phone_conversation.
Answers to structured questions are stored as top-level keys.

GET  /chat/pending-workers       — active workers with phone_verified != true
GET  /chat/state/{worker_id}     — messages + next question (single call)
POST /chat/send                  — append a free-text message
POST /chat/answer                — answer a structured question (single commit)
POST /chat/mark-verified         — set phone_verified = true
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db.database import get_db
from app.db.models import Worker, WorkerStatus
from app.services.question_flow import get_next_question, is_valid_answer
from app.services.aadhaar_service import MockDigiLockerService

router = APIRouter(prefix="/chat", tags=["chat"])


# ── Schemas ───────────────────────────────────


class PendingWorker(BaseModel):
    worker_id: str
    name: str
    phone: str
    district: str
    skill_category: str
    model_config = {"from_attributes": True}


class PendingWorkersResponse(BaseModel):
    total: int
    workers: list[PendingWorker]


class NextQuestionInfo(BaseModel):
    question_id: str | None = None
    question_text: str | None = None
    options: list[str] = []
    ui_type: str | None = None          # "buttons" or "list"
    all_answered: bool = False


class ChatStateResponse(BaseModel):
    """Single response with everything the UI needs — no extra calls."""
    worker_id: str
    messages: list[dict] = []
    next_question: NextQuestionInfo


class ChatMessage(BaseModel):
    worker_id: str
    sender: str = Field(..., description="'agent' or 'worker'")
    message: str


class ChatSendResponse(BaseModel):
    worker_id: str
    messages: list[dict] = []
    next_question: NextQuestionInfo


class AnswerRequest(BaseModel):
    worker_id: str
    question_id: str
    answer: str


class AnswerResponse(BaseModel):
    worker_id: str
    question_id: str
    answer: str
    accepted: bool
    messages: list[dict] = []
    next_question: NextQuestionInfo


class MarkVerifiedRequest(BaseModel):
    worker_id: str


class MarkVerifiedResponse(BaseModel):
    worker_id: str
    phone_verified: bool = True
    messages: list[dict] = []


# ── Helpers ───────────────────────────────────


def _get_worker_or_404(worker_id: str, db: Session) -> Worker:
    worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Worker not found")
    return worker


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_next_question(verification: dict) -> NextQuestionInfo:
    nq = get_next_question(verification)
    if nq is None:
        return NextQuestionInfo(all_answered=True)
    return NextQuestionInfo(
        question_id=nq["id"],
        question_text=nq["text"],
        options=nq["options"],
        ui_type=nq["ui_type"],
    )


def _save_verification(worker: Worker, verification: dict, db: Session):
    """Write verification_status, flag mutation, commit once."""
    worker.verification_status = verification
    worker.updated_ts = datetime.now(timezone.utc)
    flag_modified(worker, "verification_status")
    db.commit()
    db.refresh(worker)


# ── Endpoints ─────────────────────────────────


@router.get(
    "/pending-workers",
    response_model=PendingWorkersResponse,
    summary="List workers pending phone verification",
)
def list_pending_workers(db: Session = Depends(get_db)):
    rows = (
        db.query(Worker)
        .filter(
            Worker.status == WorkerStatus.ACTIVE,
            Worker.phone.isnot(None),
            Worker.phone != "",
        )
        .filter(
            text(
                "COALESCE(json_extract(verification_status, '$.phone_verified'), 0) NOT IN (1, 'true')"
            )
        )
        .order_by(Worker.created_ts.desc())
        .all()
    )
    workers = [
        PendingWorker(
            worker_id=r.worker_id,
            name=r.name,
            phone=r.phone,
            district=r.district,
            skill_category=r.skill_category.value if hasattr(r.skill_category, "value") else r.skill_category,
        )
        for r in rows
    ]
    return PendingWorkersResponse(total=len(workers), workers=workers)


@router.get(
    "/state/{worker_id}",
    response_model=ChatStateResponse,
    summary="Get full chat state — messages + next question (single call)",
    description=(
        "Returns the conversation history and the next unanswered question. "
        "If the next question hasn't been sent as an agent message yet it is "
        "automatically appended so it shows in the chat window."
    ),
)
def get_chat_state(worker_id: str, db: Session = Depends(get_db)):
    worker = _get_worker_or_404(worker_id, db)
    verification = worker.verification_status or {}
    conversation = verification.get("phone_conversation", [])

    nq_info = _build_next_question(verification)

    # Auto-send the question text as an agent message if not already the last agent msg
    # Skip when conversation is empty — let the UI send the greeting first,
    # and /send will auto-append the first question after the greeting.
    if conversation and not nq_info.all_answered and nq_info.question_text:
        last_agent_msgs = [m["message"] for m in conversation if m["sender"] == "agent"]
        if not last_agent_msgs or last_agent_msgs[-1] != nq_info.question_text:
            conversation.append({
                "sender": "agent",
                "message": nq_info.question_text,
                "timestamp": _now_iso(),
            })
            verification["phone_conversation"] = conversation
            _save_verification(worker, verification, db)

    return ChatStateResponse(
        worker_id=worker_id,
        messages=conversation,
        next_question=nq_info,
    )


@router.post(
    "/send",
    response_model=ChatSendResponse,
    summary="Send a free-text message (returns updated state)",
)
def send_message(msg: ChatMessage, db: Session = Depends(get_db)):
    worker = _get_worker_or_404(msg.worker_id, db)
    verification = worker.verification_status or {}
    conversation = verification.get("phone_conversation", [])

    conversation.append({
        "sender": msg.sender,
        "message": msg.message,
        "timestamp": _now_iso(),
    })

    # Auto-send the next question as an agent bubble if not already the last one
    nq_info = _build_next_question(verification)
    if not nq_info.all_answered and nq_info.question_text:
        last_agent_msgs = [m["message"] for m in conversation if m["sender"] == "agent"]
        if not last_agent_msgs or last_agent_msgs[-1] != nq_info.question_text:
            conversation.append({
                "sender": "agent",
                "message": nq_info.question_text,
                "timestamp": _now_iso(),
            })

    verification["phone_conversation"] = conversation
    _save_verification(worker, verification, db)

    return ChatSendResponse(
        worker_id=msg.worker_id,
        messages=conversation,
        next_question=nq_info,
    )


@router.post(
    "/answer",
    response_model=AnswerResponse,
    summary="Answer a verification question — single commit, returns full state",
)
def answer_question(req: AnswerRequest, db: Session = Depends(get_db)):
    worker = _get_worker_or_404(req.worker_id, db)
    verification = worker.verification_status or {}

    nq = get_next_question(verification)
    if nq is None or nq["id"] != req.question_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Question '{req.question_id}' is not the current pending question.",
        )

    if not is_valid_answer(nq, req.answer):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid answer '{req.answer}'. Allowed: {nq['options']}",
        )

    # Normalise casing
    normalised = next(
        opt for opt in nq["options"] if opt.lower() == req.answer.strip().lower()
    )

    conversation = verification.get("phone_conversation", [])

    # ── Special handling: Aadhaar DigiLocker verification ──
    if nq["id"] == "aadhaar_verify":
        # Worker clicked "Verify via DigiLocker" — run the full mock flow
        conversation.append({
            "sender": "worker",
            "message": normalised,
            "timestamp": _now_iso(),
        })
        conversation.append({
            "sender": "agent",
            "message": "Connecting to DigiLocker...",
            "timestamp": _now_iso(),
        })

        # 1) Initiate
        auth = MockDigiLockerService.initiate(
            worker_id=req.worker_id,
            aadhar_hash=worker.aadhar_hash,
        )
        # 2) Simulate worker clicking "Allow"
        MockDigiLockerService.complete(auth.transaction_id)
        # 3) Fetch e-KYC
        kyc = MockDigiLockerService.fetch_ekyc(
            transaction_id=auth.transaction_id,
            name=worker.name,
            dob=worker.dob.isoformat() if worker.dob else None,
            district=worker.district,
        )

        if kyc and kyc.verified:
            verification["aadhaar_verified"] = True
            verification["aadhaar_txn_id"] = auth.transaction_id
            dob_str = f"\nDOB: {kyc.dob}" if kyc.dob else ""
            conversation.append({
                "sender": "agent",
                "message": (
                    f"\u2705 Aadhaar verified via DigiLocker!\n"
                    f"Name: {kyc.name}{dob_str}\n"
                    f"District: {kyc.district or 'N/A'}"
                ),
                "timestamp": _now_iso(),
            })
        else:
            conversation.append({
                "sender": "agent",
                "message": "\u274c DigiLocker verification failed. Please try again later.",
                "timestamp": _now_iso(),
            })

        # Mark question as answered
        verification["aadhaar_verify"] = normalised

        # Auto-send next question
        next_nq = get_next_question(verification)
        nq_info = _build_next_question(verification)
        if next_nq is not None:
            conversation.append({
                "sender": "agent",
                "message": next_nq["text"],
                "timestamp": _now_iso(),
            })
        else:
            verification["phone_verified"] = True
            conversation.append({
                "sender": "agent",
                "message": "\u2705 Phone verification complete. Thank you!",
                "timestamp": _now_iso(),
            })

        verification["phone_conversation"] = conversation
        _save_verification(worker, verification, db)

        return AnswerResponse(
            worker_id=req.worker_id,
            question_id=req.question_id,
            answer=normalised,
            accepted=True,
            messages=conversation,
            next_question=nq_info if next_nq else NextQuestionInfo(all_answered=True),
        )

    # ── Standard question handling ──

    # Store the answer as a top-level key
    verification[req.question_id] = normalised

    # Append worker answer to conversation
    conversation.append({
        "sender": "worker",
        "message": normalised,
        "timestamp": _now_iso(),
    })

    # Auto-send the NEXT question as an agent message
    next_nq = get_next_question(verification)
    nq_info = _build_next_question(verification)
    if next_nq is not None:
        conversation.append({
            "sender": "agent",
            "message": next_nq["text"],
            "timestamp": _now_iso(),
        })
    else:
        # All questions answered → auto-mark phone as verified
        verification["phone_verified"] = True
        conversation.append({
            "sender": "agent",
            "message": "\u2705 Phone verification complete. Thank you!",
            "timestamp": _now_iso(),
        })

    verification["phone_conversation"] = conversation
    _save_verification(worker, verification, db)

    return AnswerResponse(
        worker_id=req.worker_id,
        question_id=req.question_id,
        answer=normalised,
        accepted=True,
        messages=conversation,
        next_question=nq_info if next_nq else NextQuestionInfo(all_answered=True),
    )


@router.post(
    "/mark-verified",
    response_model=MarkVerifiedResponse,
    summary="Mark a worker's phone as verified",
)
def mark_phone_verified(req: MarkVerifiedRequest, db: Session = Depends(get_db)):
    worker = _get_worker_or_404(req.worker_id, db)
    verification = worker.verification_status or {}

    verification["phone_verified"] = True

    # Log it in conversation
    conversation = verification.get("phone_conversation", [])
    conversation.append({
        "sender": "agent",
        "message": "✅ Phone verification complete. Thank you!",
        "timestamp": _now_iso(),
    })
    verification["phone_conversation"] = conversation

    _save_verification(worker, verification, db)

    return MarkVerifiedResponse(
        worker_id=worker.worker_id,
        phone_verified=True,
        messages=conversation,
    )
