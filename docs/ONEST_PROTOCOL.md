# ONEST / Beckn Protocol — Implementation Guide

> **Domain:** `onest:work-opportunities` · **Beckn Core version:** 1.1.0
> **BPP ID:** `onest-skill-discovery.bpp.io`

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Transaction Lifecycle](#transaction-lifecycle)
3. [API Reference — BPP Endpoints](#api-reference--bpp-endpoints)
4. [API Reference — Mock BAP Gateway](#api-reference--mock-bap-gateway)
5. [API Reference — xInput Forms](#api-reference--xinput-forms)
6. [API Reference — Registry](#api-reference--registry)
7. [Database Schema](#database-schema)
8. [Beckn Pydantic Models](#beckn-pydantic-models)
9. [Error Codes](#error-codes)
10. [ed25519 Signing & Verification](#ed25519-signing--verification)
11. [Catalog Publishing (on_search)](#catalog-publishing-on_search)
12. [Configuration & Constants](#configuration--constants)
13. [Getting Started](#getting-started)
14. [Fulfillment State Machine](#fulfillment-state-machine)

---

## Architecture Overview

```
┌──────────┐         ┌─────────────────────────────────┐         ┌──────────────┐
│          │  search  │         BPP (this node)          │  lookup  │  Mock        │
│   BAP    │────────►│  /api/bpp/search                 │◄────────│  Registry    │
│ (seeker) │  select  │  /api/bpp/select                 │         │  /api/       │
│          │  init    │  /api/bpp/init                   │         │  registry/   │
│          │  confirm │  /api/bpp/confirm                │         └──────────────┘
│          │  status  │  /api/bpp/status                 │
│          │  update  │  /api/bpp/update                 │
│          │  cancel  │  /api/bpp/cancel                 │
│          │◄────────│                                   │
│          │ on_*     │  Background tasks POST callbacks  │
│          │ callback │  to bap_uri/{on_action}           │
└──────────┘         └──────┬───────────────────┬────────┘
                            │                   │
                     ┌──────▼──────┐     ┌──────▼──────┐
                     │  SQLite DB  │     │  data/keys/ │
                     │  worker_    │     │  ed25519    │
                     │  stage      │     │  keypair    │
                     │  beckn_     │     └─────────────┘
                     │  order      │
                     │  xinput_    │
                     │  form       │
                     └─────────────┘
```

**Key principle:** Every incoming Beckn action returns an **immediate ACK** (or NACK on validation failure). The actual processing happens in a FastAPI `BackgroundTask` which builds the `on_*` callback payload and POSTs it to the BAP's callback URI (`context.bap_uri`).

---

## Transaction Lifecycle

The ONEST work-opportunities domain follows this sequence:

```
BAP                         BPP
 │                            │
 │── search ─────────────────►│   Discover available workers
 │◄──────────── on_search ────│   Catalog of matching workers
 │                            │
 │── select ─────────────────►│   Pick a specific worker/job listing
 │◄──────────── on_select ────│   Draft order with xInput form URL
 │                            │
 │  (User fills xInput forms) │
 │                            │
 │── init ───────────────────►│   Submit customer/billing details
 │◄──────────── on_init ──────│   Initialised order
 │                            │
 │── confirm ────────────────►│   Confirm the application
 │◄──────────── on_confirm ───│   Active order
 │                            │
 │── status ─────────────────►│   Check application status
 │◄──────────── on_status ────│   Current state + fulfillment status
 │                            │
 │── update ─────────────────►│   Update customer/fulfillment info
 │◄──────────── on_update ────│   Updated order
 │                            │
 │── cancel ─────────────────►│   Cancel the application
 │◄──────────── on_cancel ────│   Cancelled order
```

---

## API Reference — BPP Endpoints

All endpoints accept a Beckn-standard JSON body with `context` + `message` and return a `BecknAckResponse`.

| Method | Path | Action | Callback |
|--------|------|--------|----------|
| POST | `/api/bpp/search` | Catalog search | `on_search` |
| POST | `/api/bpp/select` | Select a job listing | `on_select` |
| POST | `/api/bpp/init` | Initialise application | `on_init` |
| POST | `/api/bpp/confirm` | Confirm application | `on_confirm` |
| POST | `/api/bpp/status` | Query order status | `on_status` |
| POST | `/api/bpp/update` | Update order | `on_update` |
| POST | `/api/bpp/cancel` | Cancel order | `on_cancel` |

### Example: Search Request

```json
{
  "context": {
    "domain": "onest:work-opportunities",
    "action": "search",
    "version": "1.1.0",
    "bap_id": "my-bap.example.com",
    "bap_uri": "https://my-bap.example.com/beckn",
    "transaction_id": "txn-uuid",
    "message_id": "msg-uuid",
    "timestamp": "2026-04-04T10:00:00Z",
    "ttl": "P1M"
  },
  "message": {
    "intent": {
      "descriptor": { "name": "plumbing" }
    }
  }
}
```

### ACK Response (immediate)

```json
{
  "message": { "ack": { "status": "ACK" } },
  "error": null
}
```

### NACK Response (validation failure)

```json
{
  "message": { "ack": { "status": "NACK" } },
  "error": {
    "type": "DOMAIN-ERROR",
    "code": "30004",
    "message": "Item abc-123 not found"
  }
}
```

### Search Behavior

- Queries `worker` table for workers with status `active` or `verified` and availability `available` or `partially_available`
- Limits to 50 results
- If `intent.descriptor.name` is provided, filters by name or skill category (case-insensitive)
- Builds a Beckn Catalog with a single Provider containing all matching Items

### Select Behavior

- Validates the requested item (worker) exists
- Creates a **DRAFT** `BecknOrder` in the database
- Creates `XInputForm` stubs (2 steps: Personal Details + Upload Documents)
- Returns the order with xInput form URLs in the `on_select` callback

### Init Behavior

- Looks up the order by `transaction_id`
- Stores `customer.person`, `customer.contact`, and `billing` from the request
- Sets fulfillment status to `APPLICATION-STARTED`

### Confirm Behavior

- Sets order state to `ACTIVE`
- Sets fulfillment status to `APPLICATION-FILLED`
- Warns if xInput forms are incomplete but still proceeds

### Cancel Behavior

- Sets order state to `CANCELLED`
- Sets fulfillment status to `CANCELLED`
- Records the cancellation reason from the request

---

## API Reference — Mock BAP Gateway

These endpoints simulate what a real BAP would host. The BPP's background tasks POST callbacks here.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/beckn/on_search` | Receives catalog |
| POST | `/api/beckn/on_select` | Receives draft order |
| POST | `/api/beckn/on_init` | Receives initialised order |
| POST | `/api/beckn/on_confirm` | Receives confirmed order |
| POST | `/api/beckn/on_status` | Receives order status |
| POST | `/api/beckn/on_update` | Receives updated order |
| POST | `/api/beckn/on_cancel` | Receives cancelled order |
| GET | `/api/beckn/logs?limit=20` | Debug: recent payloads |

All `on_*` endpoints log the payload to an in-memory ring buffer (last 100 entries) and return ACK.

---

## API Reference — xInput Forms

xInput is the Beckn mechanism for collecting additional information from the applicant during the init/confirm flow.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/xinput/form/{order_id}/{step}` | Render HTML form |
| POST | `/api/xinput/form/{order_id}/{step}/submit` | Submit form data (JSON) |
| GET | `/api/xinput/status/{order_id}` | Check completion status |

### Form Steps

| Step | Heading | Fields |
|------|---------|--------|
| 0 | Personal Details | full_name, dob, gender, phone, email, address |
| 1 | Upload Documents | aadhaar_doc_url, resume_url, notes |

### Submit Payload

```json
{
  "data": {
    "full_name": "Suresh Kumar",
    "dob": "1995-01-10",
    "gender": "Male",
    "phone": "+919000000001"
  }
}
```

### Status Response

```json
{
  "order_id": "uuid",
  "total_steps": 2,
  "submitted_steps": 1,
  "steps": [
    { "form_id": "uuid", "step_index": 0, "heading": "Personal Details", "submitted": true, "form_data": {...} },
    { "form_id": "uuid", "step_index": 1, "heading": "Upload Documents", "submitted": false, "form_data": null }
  ]
}
```

When all form steps are submitted, the order's fulfillment status is automatically advanced to `APPLICATION-FILLED`.

---

## API Reference — Registry

Mock ONEST registry for subscriber management and key exchange.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/registry/subscribe` | Register a subscriber (BPP/BAP) |
| POST | `/api/registry/on_subscribe` | Registry callback with challenge |
| GET | `/api/registry/lookup/{subscriber_id}` | Look up subscriber info |

### Subscribe Payload

```json
{
  "context": { "domain": "onest:work-opportunities" },
  "message": {
    "subscriber_id": "my-bap.example.com",
    "type": "bap",
    "cb_url": "https://my-bap.example.com/beckn",
    "domain": "onest:work-opportunities",
    "country": "IND",
    "signing_public_key": "<base64-ed25519-public-key>",
    "encryption_public_key": "<base64-key>"
  }
}
```

At startup, the BPP self-registers in the mock registry via `self_register()` so auth verification works for locally-generated callbacks.

---

## Database Schema

### Tables

#### `worker`

Core worker/job-seeker records. Includes both original platform fields and Beckn-required attributes.

| Column | Type | Description |
|--------|------|-------------|
| `worker_id` | String(36) PK | UUID, auto-generated |
| `name` | String(255) | Worker's full name |
| `dob` | Date | Date of birth |
| `gender` | String(20) | Male / Female / Other |
| `aadhar_hash` | String(64) | SHA-256 of Aadhaar number |
| `district` | String(255) | District name |
| `taluk` | String(255) | Taluk/sub-district |
| `city_village` | String(255) | City or village name |
| `state_name` | String(255) | State name (Beckn `state.name`) |
| `state_code` | String(10) | ISO state code, e.g. `KA` |
| `city_code` | String(20) | STD code, e.g. `std:080` |
| `latitude` / `longitude` | Float | GPS coordinates |
| `skill_category` | Enum | One of 18 categories (see below) |
| `iti_nsqf_level` | Integer | NSQF level 1–5 |
| `highest_qualification` | String(255) | Highest qualification |
| `languages` | JSON | `[{"code":"en","name":"English"}, ...]` |
| `skills_detailed` | JSON | `[{"code":"PLUMBER","name":"Plumber"}, ...]` |
| `availability_status` | Enum | available / unavailable / partially_available |
| `preferred_shift` | Enum | morning / afternoon / evening / night / flexible |
| `fulfillment_type` | Enum | REMOTE / HYBRID / ONSITE |
| `verification_status` | JSON | Flexible verification data |
| `phone` | String(15) | Phone number |
| `email` | String(255) | Email address |
| `experience_years` | Float | Years of experience |
| `source_channel` | Enum | csv / telegram / chat_simulator / api / manual |
| `status` | Enum | active / verified / pending_verification / ... |
| `created_ts` / `updated_ts` | DateTime | Auto-managed timestamps |

#### `beckn_order`

Tracks the Beckn transaction lifecycle from select through confirm/cancel.

| Column | Type | Description |
|--------|------|-------------|
| `order_id` | String(36) PK | UUID |
| `transaction_id` | String(100) | Unique, indexed — ties all actions together |
| `message_id` | String(100) | Last message ID |
| `bap_id` / `bap_uri` | String | BAP identity & callback URL |
| `worker_id` | String(36) FK | Links to `worker` |
| `item_id` / `provider_id` | String | Beckn item & provider IDs |
| `state` | Enum | DRAFT → ACTIVE → COMPLETE / CANCELLED |
| `fulfillment_status` | Enum | See [Fulfillment State Machine](#fulfillment-state-machine) |
| `fulfillment_type` | Enum | REMOTE / HYBRID / ONSITE |
| `customer_person` | JSON | Applicant's person object |
| `customer_contact` | JSON | Applicant's contact info |
| `billing` | JSON | Billing details |
| `xinput_required` | Integer | Total form steps required |
| `xinput_submitted` | Integer | Completed form steps |
| `cancellation_reason` | Text | Reason if cancelled |
| `created_ts` / `updated_ts` | DateTime | Auto-managed |

#### `xinput_form`

Individual form steps within an order's xInput flow.

| Column | Type | Description |
|--------|------|-------------|
| `form_id` | String(36) PK | UUID |
| `order_id` | String(36) FK | Parent order |
| `transaction_id` | String(100) | Beckn transaction ID |
| `step_index` | Integer | 0-based step number |
| `heading` | String(255) | Form step heading |
| `form_data` | JSON | Submitted form data |
| `submitted` | Integer | 0 = pending, 1 = submitted |
| `created_ts` | DateTime | Creation timestamp |

### Enums

| Enum | Values |
|------|--------|
| **SkillCategory** (18) | plumbing, electrical, carpentry, welding, masonry, painting, hvac, tailoring, driving, cooking, housekeeping, gardening, security, delivery, construction, mechanic, beauty, other |
| **SourceChannel** (5) | csv, telegram, chat_simulator, api, manual |
| **WorkerStatus** (6) | active, old_duplicate, pending_verification, verified, rejected, inactive |
| **AvailabilityStatus** (3) | available, unavailable, partially_available |
| **PreferredShift** (5) | morning, afternoon, evening, night, flexible |
| **FulfillmentType** (3) | REMOTE, HYBRID, ONSITE |
| **FulfillmentStatusCode** (7) | APPLICATION-STARTED, APPLICATION-FILLED, UNDER-REVIEW, OFFER-EXTENDED, ACCEPTED, REJECTED, CANCELLED |
| **OrderState** (4) | DRAFT, ACTIVE, COMPLETE, CANCELLED |

---

## Beckn Pydantic Models

All Beckn protocol models live in `app/api/beckn_schemas.py`.

### Primitives

`Descriptor` · `TagDescriptor` · `TagListItem` · `Tag` · `City` · `State` · `Country` · `Location` · `ItemQuantity` · `TimeRange` · `Time` · `Person` · `Contact` · `Customer` · `FulfillmentState`

### Mid-level Objects

`Fulfillment` · `XInputFormHead` · `XInputForm` · `XInput` · `Item` · `Provider` · `Billing` · `Quotation` · `Payment` · `Document` · `Cancellation`

### Top-level

`Order` · `Catalog` · `Context`

### ACK / Error

`Ack` · `AckMessage` · `BecknError` · `BecknAckResponse`

### Action Pairs

Each Beckn action has a Request model (BAP → BPP) and an `On*` callback Request model (BPP → BAP):

| Action | Request → BPP | Callback → BAP |
|--------|---------------|----------------|
| search | `SearchRequest` | `OnSearchRequest` |
| select | `SelectRequest` | `OnSelectRequest` |
| init | `InitRequest` | `OnInitRequest` |
| confirm | `ConfirmRequest` | `OnConfirmRequest` |
| status | `StatusRequest` | `OnStatusRequest` |
| update | `UpdateRequest` | `OnUpdateRequest` |
| cancel | `CancelRequest` | `OnCancelRequest` |

### Registry

`SubscriberInfo` · `SubscribeRequest` · `OnSubscribeRequest`

### Tag Alias Note

The `Tag` model uses `items` as the Python field name with `alias="list"` (because `list` is a Python keyword). When serializing, always use `by_alias=True`:

```python
tag.model_dump(by_alias=True)
# → {"list": [...], "descriptor": {...}, "display": true}
```

---

## Error Codes

ONEST-standard error codes used across all BPP endpoints:

| Code | Type | Default Message |
|------|------|-----------------|
| 10000 | CONTEXT-ERROR | Invalid Context |
| 10001 | CONTEXT-ERROR | Invalid domain |
| 20000 | CORE-ERROR | Internal Server Error |
| 30000 | DOMAIN-ERROR | Provider not found |
| 30001 | DOMAIN-ERROR | Provider location not found |
| 30004 | DOMAIN-ERROR | Item not found |
| 30009 | DOMAIN-ERROR | Fulfillment agent not available |
| 40000 | POLICY-ERROR | Business policy error |
| 40001 | POLICY-ERROR | Action not applicable |
| 40002 | POLICY-ERROR | Order not found |
| 40003 | POLICY-ERROR | Order cannot be updated |
| 40004 | POLICY-ERROR | Order cannot be cancelled |
| 50000 | JSON-SCHEMA-ERROR | Invalid JSON |
| 50001 | JSON-SCHEMA-ERROR | Missing required fields |

Usage:

```python
from app.api.beckn_schemas import nack_response, ack_response

# Return a NACK with error
return nack_response("30004", "Worker xyz not found")

# Return a standard ACK
return ack_response()
```

---

## ed25519 Signing & Verification

Located in `app/services/auth.py`. Implements the Beckn authorization header scheme.

### Key Management

- Keypair auto-generated on first run and saved to `data/keys/signing_private.key` and `data/keys/signing_public.key`
- 32-byte ed25519 keys via PyNaCl
- Falls back to stub keys if PyNaCl is not installed (dev mode)

### Outgoing Request Signing

```python
from app.services.auth import sign_payload

headers = sign_payload(payload_dict, subscriber_id="onest-skill-discovery.bpp.io")
# headers = {
#   "Authorization": 'Signature keyId="onest-skill-discovery.bpp.io|key1|ed25519",...',
#   "Digest": "BLAKE-512=<base64>"
# }
```

**Signing string format:**
```
(created): {unix_timestamp}
(expires): {unix_timestamp + 300}
digest: BLAKE-512={base64_blake2b_512_hash}
```

### Incoming Request Verification

```python
from app.services.auth import verify_request

is_valid, error_msg = verify_request(auth_header, digest_header, body_bytes)
```

### Middleware (Optional)

Enable by uncommenting in `app/main.py`:

```python
from app.services.auth import verify_beckn_auth_middleware
app.middleware("http")(verify_beckn_auth_middleware)
```

When enabled, all `/api/bpp/*` requests must include valid `Authorization` and `Digest` headers. Requests without these headers are allowed through in dev mode.

---

## Catalog Publishing (on_search)

The `app/services/onest_catalog.py` module builds Beckn-compliant `on_search` payloads and publishes them to the network.

### CatalogEntry Dataclass

```python
@dataclass
class CatalogEntry:
    worker_id: str
    name: str
    district: str
    skill_category: str
    phone: str
    dob: str | None = None
```

### Payload Structure

Each published worker becomes:
- A **Provider** (`ONEST Skill Discovery Node`)
- With one **Location** (derived from district)
- One **Fulfillment** (type: ONSITE)
- One **Item** per worker with:
  - `listing-details` tag: industry-type, employment-type, job-role
  - `salary-info` tag: gross-min (180000), gross-max (360000)

### Usage

```python
from app.services.onest_catalog import publish_to_onest, CatalogEntry

entry = CatalogEntry(
    worker_id="uuid",
    name="Ramesh Kumar",
    district="Bengaluru Urban",
    skill_category="plumbing",
    phone="+919876543210",
)
success = publish_to_onest(entry)  # POSTs to mock gateway
```

---

## Configuration & Constants

| Constant | Value | Location |
|----------|-------|----------|
| `BPP_ID` | `onest-skill-discovery.bpp.io` | `bpp.py`, `onest_catalog.py` |
| `BPP_URI` | `https://onest-skill-discovery.bpp.io` | `bpp.py`, `onest_catalog.py` |
| `MOCK_GATEWAY_URL` | `http://127.0.0.1:8000/api/beckn/on_search` | `onest_catalog.py` |
| `XINPUT_BASE_URL` | `http://127.0.0.1:8000/api/xinput` | `bpp.py` |
| `XINPUT_TOTAL_STEPS` | `2` | `bpp.py` |
| `CALLBACK_TIMEOUT` | `5` seconds | `beckn_callback.py` |
| `KEYS_DIR` | `data/keys/` | `auth.py` |
| `DATABASE_URL` | `sqlite:///./data/onest_workers.db` | `database.py` |

---

## Getting Started

### Prerequisites

```
Python 3.12+
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Server

```bash
# Option 1: Uvicorn directly
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Option 2: run.py (starts FastAPI + Streamlit UI)
python run.py
```

### Quick Test — Full Lifecycle

```bash
# 1. Health check
curl http://127.0.0.1:8000/health

# 2. Create a worker
curl -X POST http://127.0.0.1:8000/api/workers/stage \
  -H "Content-Type: application/json" \
  -d '{"name":"Raju","aadhar_hash":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","district":"Bengaluru","skill_category":"plumbing","phone":"+919876543210","source_channel":"api"}'

# 3. Search via BPP
curl -X POST http://127.0.0.1:8000/api/bpp/search \
  -H "Content-Type: application/json" \
  -d '{"context":{"domain":"onest:work-opportunities","action":"search","version":"1.1.0","bap_id":"test-bap","bap_uri":"http://127.0.0.1:8000/api/beckn","transaction_id":"txn-1","message_id":"msg-1","timestamp":"2026-04-04T00:00:00Z","ttl":"P1M"},"message":{"intent":{"descriptor":{"name":"plumbing"}}}}'

# 4. Check gateway logs for the on_search callback
curl http://127.0.0.1:8000/api/beckn/logs?limit=5
```

### Interactive Docs

OpenAPI / Swagger UI available at: `http://127.0.0.1:8000/docs`

---

## Fulfillment State Machine

```
                 ┌─────────────────┐
                 │ APPLICATION-     │  (select creates DRAFT order)
                 │ STARTED          │
                 └────────┬────────┘
                          │ init / xInput submitted
                          ▼
                 ┌─────────────────┐
                 │ APPLICATION-     │  (confirm → order ACTIVE)
                 │ FILLED           │
                 └────────┬────────┘
                          │ BPP reviews
                          ▼
                 ┌─────────────────┐
                 │ UNDER-REVIEW     │
                 └────────┬────────┘
                         ╱ ╲
                        ╱   ╲
                       ▼     ▼
          ┌─────────────┐   ┌─────────────┐
          │ OFFER-       │   │ REJECTED     │
          │ EXTENDED     │   └─────────────┘
          └──────┬──────┘
                 │ Applicant accepts
                 ▼
          ┌─────────────┐
          │ ACCEPTED     │  (order → COMPLETE)
          └─────────────┘

  At any point:
          ┌─────────────┐
          │ CANCELLED    │  (cancel action, order → CANCELLED)
          └─────────────┘
```

**Order state transitions:**

| From | To | Trigger |
|------|----|---------|
| — | DRAFT | `select` |
| DRAFT | ACTIVE | `confirm` |
| ACTIVE | COMPLETE | Fulfillment reaches ACCEPTED |
| DRAFT / ACTIVE | CANCELLED | `cancel` |

---

## File Map

```
app/
├── api/
│   ├── beckn_gateway.py    # Mock BAP — receives on_* callbacks
│   ├── beckn_schemas.py     # All Beckn Pydantic models (517 lines)
│   ├── bpp.py               # BPP endpoints — search/select/init/confirm/status/update/cancel
│   ├── registry.py          # Mock registry — subscribe/on_subscribe/lookup
│   ├── xinput.py            # xInput form hosting + submission
│   ├── workers.py           # Worker CRUD API
│   ├── chat.py              # Chat simulator API
│   ├── aadhaar.py           # Aadhaar verification API
│   └── schemas.py           # Worker Pydantic request/response schemas
├── db/
│   ├── database.py          # SQLite engine + session factory
│   └── models.py            # ORM models — worker, beckn_order, xinput_form
├── services/
│   ├── auth.py              # ed25519 signing/verification + middleware
│   ├── beckn_callback.py    # HTTP callback poster (on_* → BAP)
│   ├── onest_catalog.py     # Builds on_search payloads for the catalog
│   ├── aadhaar_service.py   # Mock DigiLocker service
│   └── question_flow.py     # Chat verification question flow
├── schedulers/
│   └── verification_poller.py  # Background poller (30s interval)
└── main.py                  # FastAPI app entry point
```
