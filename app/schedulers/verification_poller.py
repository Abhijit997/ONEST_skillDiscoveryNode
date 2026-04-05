"""
Verification Poller — background task that runs every 30 seconds.

Looks for workers where BOTH aadhaar_verified and phone_verified are true
but status is still 'active' (not yet promoted to 'verified').

Action on match:
    Promote worker status → 'verified'  (makes them discoverable via /search)
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm.attributes import flag_modified

from app.db.database import SessionLocal
from app.db.models import Worker, WorkerStatus
from app.services.emb_worker_service import insert_worker_embedding_from_sqlite

log = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30


def _process_fully_verified_workers() -> int:
    """
    Find workers with both verifications complete but not yet promoted.
    Returns the number of workers processed.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(Worker)
            .filter(
                Worker.status == WorkerStatus.ACTIVE,
            )
            .filter(
                text(
                    "json_extract(verification_status, '$.aadhaar_verified') = 1"
                    " AND json_extract(verification_status, '$.phone_verified') = 1"
                )
            )
            .all()
        )

        if not rows:
            return 0

        count = 0
        for worker in rows:
            # Promote status to 'verified'
            worker.status = WorkerStatus.VERIFIED
            worker.updated_ts = datetime.now(timezone.utc)

            # Record promotion timestamp in verification_status
            vs = worker.verification_status or {}
            vs["onest_discoverable"] = True
            vs["verified_ts"] = datetime.now(timezone.utc).isoformat()
            worker.verification_status = vs
            # Embed worker in ChromaDB
            try:
                insert_worker_embedding_from_sqlite(db, worker.worker_id)
                log.info("EMBEDDED | worker_id=%s | name=%s into ChromaDB", worker.worker_id, worker.name)
            except Exception:
                log.exception("Failed to embed worker_id=%s in ChromaDB", worker.worker_id)
            flag_modified(worker, "verification_status")

            count += 1
            log.info(
                "VERIFIED | worker_id=%s | name=%s → status=verified (now discoverable)",
                worker.worker_id,
                worker.name,
            )

        if count:
            db.commit()
            log.info("Verification poller: %d worker(s) promoted to verified.", count)

        return count
    except Exception:
        db.rollback()
        log.exception("Verification poller error")
        return 0
    finally:
        db.close()


async def verification_poller():
    """Async loop that polls every POLL_INTERVAL_SECONDS."""
    log.info(
        "Verification poller started (interval=%ds)", POLL_INTERVAL_SECONDS
    )
    while True:
        try:
            _process_fully_verified_workers()
        except Exception:
            log.exception("Verification poller unexpected error")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
