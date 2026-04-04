# Aadhaar Verification via DigiLocker — Architecture & Flow

## Why DigiLocker?

| Method | Cost per verification | License needed | Worker effort | Data returned |
|---|---|---|---|---|
| **DigiLocker OAuth** | **Free** (govt API) | Integration Partner (free registration) | Tap "Allow" (like Sign in with Google) | Name, DOB, gender, address, photo |
| Aadhaar OTP (via Signzy/Digio/Karza) | ₹2–15 | Sub-AUA agreement | Enter Aadhaar + OTP | Name, DOB, gender, address, photo |
| Biometric (fingerprint/iris) | ₹5–20 | AUA + certified device | Visit centre / use device | Yes/No authentication |
| Offline XML download | Free | None | Visit myaadhaar.uidai.gov.in, download zip, share with 4-digit code | Name, DOB, address, photo (signed) |
| mAadhaar QR scan | Free | None | Open app, show QR | Name, DOB, address, photo (signed) |
| Penny Drop (bank verification) | ₹1–2 | Payment gateway | Share bank account | Name only |

**Decision**: DigiLocker is the only method that is:
- **Free** at scale (no per-transaction cost)
- **Fully digital** (no physical device or in-person visit)
- **Low friction** for workers (single tap to authorize)
- **Returns full KYC** (name, DOB, address, photo — digitally signed by UIDAI)
- **Government-sanctioned** (official UIDAI issuer via DigiLocker)

---

## Transaction Flow — Step by Step

### Overview

```
Chat UI  →  Chat API (/answer)  →  MockDigiLockerService  →  DB
                                    (production: real DigiLocker API)
```

In the chat simulator, all 3 DigiLocker steps happen **server-side within a single `/answer` API call**. In production, steps 1–2 would involve a browser redirect to DigiLocker's login page.

---

### Step 1: Initiate (`MockDigiLockerService.initiate()`)

**When**: Worker clicks "Verify via DigiLocker" button in chat.

**Input**:
```json
{
  "worker_id": "9f93adf3-dd87-4a89-92ba-e646e1ad2328",
  "aadhar_hash": "b822bb93905a9bd8b3a0c08168c427696436cf8bf37ed4ab8ebf41a07642ed1c"
}
```

**What happens**:
1. Generates a unique transaction ID: `TXN-20260404172759-0b6681a3`
2. Builds a mock DigiLocker authorization URL:
   ```
   https://digilocker.meripehchaan.gov.in/public/oauth2/1/authorize
     ?client_id=MOCK_CLIENT_ID
     &redirect_uri=http://localhost:8000/api/aadhaar/callback
     &response_type=code
     &state=TXN-20260404172759-0b6681a3
   ```
3. Creates a masked Aadhaar string from the hash: `XXXX-XXXX-d1c`
4. Stores the transaction in-memory (`_pending` dict) with status `"pending"`

**Output**:
```python
DigiLockerAuthResult(
    transaction_id="TXN-20260404172759-0b6681a3",
    auth_url="https://digilocker.meripehchaan.gov.in/...",
    masked_aadhaar="XXXX-XXXX-d1c"
)
```

**Production equivalent**: 
`POST https://digilocker.meripehchaan.gov.in/public/oauth2/1/authorize` — redirects worker to DigiLocker login page where they enter Aadhaar + OTP (OTP sent by UIDAI to their registered mobile).

---

### Step 2: Callback / Complete (`MockDigiLockerService.complete()`)

**When**: Simulates the worker clicking "Allow" on DigiLocker's consent screen.

**Input**:
```json
{
  "transaction_id": "TXN-20260404172759-0b6681a3"
}
```

**What happens**:
1. Looks up transaction in `_pending` dict
2. Changes status from `"pending"` → `"authorized"`

**Output**: `True` (success) or `False` (not found)

**Production equivalent**:
DigiLocker redirects back to your `redirect_uri` with an authorization code:
```
GET http://localhost:8000/api/aadhaar/callback
  ?code=AUTH_CODE_FROM_DIGILOCKER
  &state=TXN-20260404172759-0b6681a3
```
Your backend then exchanges this code for an access token:
```
POST https://digilocker.meripehchaan.gov.in/public/oauth2/1/token
  grant_type=authorization_code
  &code=AUTH_CODE_FROM_DIGILOCKER
  &client_id=YOUR_CLIENT_ID
  &client_secret=YOUR_CLIENT_SECRET
  &redirect_uri=http://localhost:8000/api/aadhaar/callback
```

---

### Step 3: Fetch e-KYC (`MockDigiLockerService.fetch_ekyc()`)

**When**: Immediately after step 2 completes successfully.

**Input**:
```json
{
  "transaction_id": "TXN-20260404172759-0b6681a3",
  "name": "Abhijit Banerjee",
  "dob": "1990-01-15",
  "district": "WB"
}
```
*(name, dob, district come from our `worker_stage` table — in production, they'd come from DigiLocker's response)*

**What happens**:
1. Looks up transaction — must be `"authorized"`
2. Changes status from `"authorized"` → `"completed"`
3. Returns worker's data as if DigiLocker sent it

**Output**:
```python
DigiLockerKYC(
    transaction_id="TXN-20260404172759-0b6681a3",
    verified=True,
    name="Abhijit Banerjee",
    dob="1990-01-15",
    gender=None,
    district="WB",
    state=None,
    pincode=None,
    photo_base64=None
)
```

**Production equivalent**:
```
GET https://digilocker.meripehchaan.gov.in/public/oauth2/2/xml/eaadhaar
  Authorization: Bearer ACCESS_TOKEN_FROM_STEP_2
```
Returns XML with UIDAI-signed Aadhaar data (name, DOB, gender, address, photo).

---

## Data Storage

After successful verification, the following is written to `worker_stage.verification_status` (JSON column):

```json
{
  "aadhaar_verified": true,
  "aadhaar_txn_id": "TXN-20260404172759-0b6681a3",
  "aadhaar_verify": "Verify via DigiLocker",
  "phone_verified": false,
  "address_verified": false,
  "phone_conversation": [
    { "sender": "agent", "message": "Hello Abhijit! Welcome to ONEST...", "timestamp": "..." },
    { "sender": "agent", "message": "To verify your identity, please authorize via DigiLocker.", "timestamp": "..." },
    { "sender": "worker", "message": "Verify via DigiLocker", "timestamp": "..." },
    { "sender": "agent", "message": "Connecting to DigiLocker...", "timestamp": "..." },
    { "sender": "agent", "message": "✅ Aadhaar verified via DigiLocker!\nName: Abhijit Banerjee\nDOB: 1990-01-15\nDistrict: WB", "timestamp": "..." },
    { "sender": "agent", "message": "Are you available to start work in the next 14 days?", "timestamp": "..." }
  ]
}
```

| Key | Type | Purpose |
|---|---|---|
| `aadhaar_verified` | `bool` | Whether Aadhaar has been verified |
| `aadhaar_txn_id` | `string` | DigiLocker transaction ID for audit trail |
| `aadhaar_verify` | `string` | The answer stored by question_flow (marks question as done) |
| `phone_conversation` | `list[dict]` | Full chat history including verification messages |

---

## Where Each Piece Lives

| Component | File | Purpose |
|---|---|---|
| Mock service | `app/services/aadhaar_service.py` | `MockDigiLockerService` — 3 class methods (initiate, complete, fetch_ekyc) |
| Standalone API | `app/api/aadhaar.py` | 4 REST endpoints for direct API usage |
| Chat integration | `app/api/chat.py` → `answer_question()` | Special `aadhaar_verify` branch runs all 3 steps in one call |
| Question config | `app/services/question_flow.py` | `aadhaar_verify` is first question in QUESTIONS list |
| DB storage | `app/db/models.py` → `WorkerStage.verification_status` | JSON column stores verified flag + transaction ID |

---

## Mock vs Production — What Changes

| Component | Mock (current) | Production |
|---|---|---|
| `initiate()` | Generates local transaction ID + fake URL | Calls DigiLocker Partner API, gets real auth URL |
| `complete()` | Flips in-memory status to "authorized" | Receives real callback from DigiLocker with auth code, exchanges for access token |
| `fetch_ekyc()` | Returns worker's own DB data | Calls DigiLocker e-KYC API with access token, gets UIDAI-signed data |
| Transaction store | In-memory dict (lost on restart) | Database table or Redis |
| Chat UX | Button click → instant verification | Button opens DigiLocker in browser → worker logs in → callback updates chat |
| Swap effort | Replace `MockDigiLockerService` with `RealDigiLockerService` | Same interface, different implementation |

---

## Production Registration

To use DigiLocker in production:
1. Register at https://partners.digitallocker.gov.in
2. Get `client_id` and `client_secret`
3. Set up `redirect_uri` (your callback URL, must be HTTPS)
4. Implement `RealDigiLockerService` with the same 3-method interface
5. No per-transaction cost — DigiLocker API is free for registered partners
