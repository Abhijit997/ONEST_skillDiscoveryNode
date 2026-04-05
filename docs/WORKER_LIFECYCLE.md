# Worker Lifecycle

Complete status lifecycle for a worker record in the `worker` table, from ingestion to ONEST discovery.

---

## Status Diagram

```
                   ┌──────────────────────────────────────────────────┐
                   │              INGESTION                           │
                   │  CSV / Telegram / Chat / API / Manual            │
                   └───────────────────┬──────────────────────────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                     ┌───────►│     ACTIVE       │◄─────── default status on insert
                     │        └────────┬─────────┘
                     │                 │
          (re-insert │     ┌───────────┼───────────────┐
           same      │     │           │               │
           Aadhaar)  │     ▼           ▼               ▼
                     │  Aadhaar     Phone           Both verifications
                     │  verify      verify          NOT completed
                     │  via         via             (manual reject)
                     │  DigiLocker  Chat                │
                     │     │           │               ▼
                     │     │           │      ┌─────────────────┐
                     │     │           │      │    REJECTED     │
                     │     │           │      └─────────────────┘
                     │     ▼           ▼
                     │   aadhaar_    phone_
                     │   verified    verified
                     │   = true      = true
                     │     │           │
                     │     └─────┬─────┘
                     │           │
                     │           ▼
                     │  ┌────────────────────┐
                     │  │ Verification Poller │  (every 30 seconds)
                     │  │ checks BOTH flags   │
                     │  └────────┬───────────┘
                     │           │
                     │           ▼
                     │  ┌─────────────────┐
                     │  │    VERIFIED      │───── discoverable via ONEST /search
                     │  └────────┬────────┘
                     │           │
                     │           │  (manual deactivation)
                     │           ▼
                     │  ┌─────────────────┐
                     │  │    INACTIVE      │───── hidden from catalog
                     │  └─────────────────┘
                     │
                     │
              ┌──────┴──────────┐
              │  OLD_DUPLICATE   │───── previous record for same Aadhaar
              └─────────────────┘
```

---

## Status Reference

| Status | Value | Description | In ONEST Catalog? |
|--------|-------|-------------|:------------------:|
| **ACTIVE** | `active` | Newly ingested worker, awaiting verification | **Yes** |
| **VERIFIED** | `verified` | Both Aadhaar + phone verified by system | **Yes** |
| **PENDING_VERIFICATION** | `pending_verification` | Reserved for explicit verification queue (not auto-set currently) | No |
| **OLD_DUPLICATE** | `old_duplicate` | Superseded by a newer record with the same Aadhaar hash | No |
| **REJECTED** | `rejected` | Failed verification or manually rejected | No |
| **INACTIVE** | `inactive` | Manually deactivated (worker opted out, admin action, etc.) | No |

> **Catalog visibility rule:** Only workers with status `active` or `verified` **AND** availability `available` or `partially_available` appear in ONEST `/search` results.

---

## Step-by-Step Lifecycle

### 1. Ingestion → `ACTIVE`

**Trigger:** Worker data enters the system via any channel.

| Channel | Endpoint / Method | Notes |
|---------|-------------------|-------|
| CSV upload | `POST /api/workers` or `/upsert` | Bulk import |
| Telegram bot | `POST /api/workers/upsert` | Conversational onboarding |
| Chat simulator | `POST /api/workers/upsert` | Testing/demo |
| Direct API | `POST /api/workers` | Third-party integration |
| Manual | `POST /api/workers` | Admin entry |

**What happens:**
- Worker record created with `status = active`
- `verification_status = {}` (empty JSON)
- If using `/upsert` and a previous record exists with the same `aadhar_hash`, the old record(s) are marked `old_duplicate` (see step 6)
- Geocoding auto-fills lat/lon, state_name, state_code from PIN code if not provided

**File:** `app/api/workers.py` → `_create_worker_record()`, `insert_worker()`, `upsert_worker()`

---

### 2. Aadhaar Verification → `verification_status.aadhaar_verified = true`

**Trigger:** Initiated via chat flow or standalone Aadhaar API.

| Method | Endpoint |
|--------|----------|
| Chat flow | `POST /api/chat/answer` with `question_id = "aadhaar_verify"` |
| Standalone | `POST /api/aadhaar/initiate` → `/callback` → `/fetch-document` |

**What happens (3-step DigiLocker mock flow):**

1. **Initiate** — Creates a pending transaction, returns auth URL
2. **Callback** — Simulates user authorization, marks transaction `authorized`
3. **Fetch Document** — Retrieves eKYC data, sets:
   ```json
   {
     "aadhaar_verified": true,
     "aadhaar_txn_id": "TXN-..."
   }
   ```

**Status does NOT change** — worker remains `active`. Only the JSON `verification_status` column is updated.

**Files:** `app/api/aadhaar.py`, `app/api/chat.py`, `app/services/aadhaar_service.py`

---

### 3. Phone Verification → `verification_status.phone_verified = true`

**Trigger:** Chat-based question flow completed by the worker.

| Step | Endpoint |
|------|----------|
| Get questions | `GET /api/chat/state/{worker_id}` |
| Answer each | `POST /api/chat/answer` |
| Mark verified | `POST /api/chat/mark-verified` |

**What happens:**
- Agent asks verification questions (availability, language, experience, etc.)
- Each answer is recorded in `verification_status.phone_conversation[]`
- When all questions are answered, agent or system calls `/mark-verified`
- Sets:
  ```json
  {
    "phone_verified": true
  }
  ```

**Status does NOT change** — worker remains `active`. Only the JSON `verification_status` column is updated.

**Files:** `app/api/chat.py`, `app/services/question_flow.py`

---

### 4. Auto-Promotion → `VERIFIED`

**Trigger:** Background verification poller (runs every 30 seconds).

**Condition:** All three must be true:
1. `status == active`
2. `verification_status.aadhaar_verified == true`
3. `verification_status.phone_verified == true`

**What happens:**
```
status:  active  →  verified
verification_status += {
    "onest_discoverable": true,
    "verified_ts": "2026-04-04T12:00:00+00:00"
}
```

**Effect:** Worker is now fully trusted. Still appears in ONEST catalog (was already visible as `active`, now has stronger trust signal).

**File:** `app/schedulers/verification_poller.py` → `_process_fully_verified_workers()`

---

### 5. Discovery via ONEST

**Trigger:** BAP sends `POST /api/bpp/search`.

**Query filter applied:**
```python
Worker.status.in_(["active", "verified"])
Worker.availability_status.in_(["available", "partially_available"])
```

Both `active` and `verified` workers are returned. The catalog does not distinguish between them in the Beckn response — this is intentional to allow newly-ingested workers to be discovered while verification is in progress.

**File:** `app/api/bpp.py` → `_handle_search()`

---

### 6. Duplicate Handling → `OLD_DUPLICATE`

**Trigger:** New record inserted via `/upsert` with an `aadhar_hash` that already exists.

**What happens:**
- All existing records with the same `aadhar_hash` (except those already `old_duplicate`) get:
  ```
  status:  *  →  old_duplicate
  ```
- New record is created with `status = active`
- Returns count of duplicates marked

**Effect:** Old records are hidden from catalog and search results. Only the latest record for a given Aadhaar is active.

**File:** `app/api/workers.py` → `upsert_worker()`

---

### 7. Manual Rejection → `REJECTED`

**Trigger:** Admin action via API (update worker status directly).

**Use cases:**
- Failed verification (e.g., Aadhaar data mismatch in production)
- Fraudulent profile detected
- Policy violation

**Effect:** Worker is hidden from ONEST catalog immediately.

> *Currently no automated rejection flow exists. This status is reserved for manual/admin operations.*

---

### 8. Manual Deactivation → `INACTIVE`

**Trigger:** Admin action or worker opt-out.

**Use cases:**
- Worker requests removal from platform
- Seasonal unavailability
- Administrative suspension

**Effect:** Worker is hidden from ONEST catalog. Can be reactivated by setting status back to `active`.

> *Currently no automated deactivation flow exists. This status is reserved for manual/admin operations.*

---

## Verification Status JSON Structure

The `verification_status` column (JSON) accumulates data through the lifecycle:

```json
{
  "aadhaar_verified": true,
  "aadhaar_txn_id": "TXN-20260404172759-0b6681a3",
  "aadhaar_verify": "Verify via DigiLocker",
  "phone_verified": true,
  "phone_conversation": [
    { "sender": "agent", "message": "Hello! Welcome to ONEST...", "timestamp": "..." },
    { "sender": "worker", "message": "Yes", "timestamp": "..." }
  ],
  "onest_discoverable": true,
  "verified_ts": "2026-04-04T12:00:00+00:00"
}
```

| Key | Set By | When |
|-----|--------|------|
| `aadhaar_verified` | Aadhaar API / Chat | After DigiLocker eKYC fetch |
| `aadhaar_txn_id` | Aadhaar API / Chat | After DigiLocker eKYC fetch |
| `phone_verified` | Chat API | After `/mark-verified` |
| `phone_conversation` | Chat API | Each message sent/received |
| `onest_discoverable` | Verification poller | On promotion to `verified` |
| `verified_ts` | Verification poller | On promotion to `verified` |

---

## Status Transitions Summary

```
INSERT (any channel)          →  active
upsert (same Aadhaar exists)  →  old records: old_duplicate
                                 new record: active
Aadhaar + Phone verified      →  verified       (auto, poller)
Admin reject                  →  rejected       (manual)
Admin deactivate              →  inactive       (manual)
Admin reactivate              →  active         (manual)
```

---

## Related Files

| File | Role |
|------|------|
| `app/db/models.py` | `Worker` model, `WorkerStatus` enum (6 values) |
| `app/api/workers.py` | Insert, upsert (dedup), search, delete endpoints |
| `app/api/chat.py` | Phone verification chat flow |
| `app/api/aadhaar.py` | Standalone Aadhaar verification endpoints |
| `app/services/aadhaar_service.py` | Mock DigiLocker service |
| `app/services/question_flow.py` | Chat verification question definitions |
| `app/schedulers/verification_poller.py` | Background poller: `active` → `verified` promotion |
| `app/api/bpp.py` | ONEST catalog search (filters by status + availability) |
