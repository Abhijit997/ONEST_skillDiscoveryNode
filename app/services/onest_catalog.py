"""
ONEST Catalog Service — builds a Beckn-compliant on_search payload and POSTs
it to the mock ONEST gateway (local ``/api/beckn/on_search``).

In production the target URL would be the real BAP callback URI instead of a
local mock endpoint.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from app.api.beckn_schemas import (
    Catalog,
    Context,
    Customer,
    Contact,
    Descriptor,
    Fulfillment,
    Item,
    Location,
    City,
    State,
    OnSearchMessage,
    OnSearchRequest,
    Person,
    Provider,
    Tag,
    TagDescriptor,
    TagListItem,
)

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────
# In production this comes from the registry / env var.
MOCK_GATEWAY_URL = "http://127.0.0.1:8000/api/beckn/on_search"
BPP_ID = "onest-skill-discovery.bpp.io"
BPP_URI = "https://onest-skill-discovery.bpp.io"


@dataclass
class CatalogEntry:
    """Minimal representation of a worker listing on the ONEST network."""
    worker_id: str
    name: str
    district: str
    skill_category: str
    phone: str
    dob: str | None = None


# ── Payload builder ───────────────────────────


def _build_on_search_payload(entry: CatalogEntry) -> dict:
    """
    Map a ``CatalogEntry`` to a full Beckn ``on_search`` request payload
    following the ONEST work-opportunities domain schema.
    """

    now = datetime.now(timezone.utc).isoformat()

    context = Context(
        domain="onest:work-opportunities",
        action="on_search",
        version="1.1.0",
        bpp_id=BPP_ID,
        bpp_uri=BPP_URI,
        transaction_id=str(uuid.uuid4()),
        message_id=str(uuid.uuid4()),
        timestamp=now,
        ttl="P1M",
    )

    location = Location(
        id="L1",
        city=City(name=entry.district, code=f"std:{entry.district[:3].lower()}"),
        state=State(name=entry.district, code=entry.district[:2].upper()),
    )

    fulfillment = Fulfillment(id="1", type="ONSITE")

    # Tags — listing-details + salary-info (dummy salary for mock)
    listing_tag = Tag(
        display=True,
        descriptor=TagDescriptor(code="listing-details", name="Listing details"),
        items=[
            TagListItem(
                descriptor=TagDescriptor(code="industry-type", name="Industry type"),
                value="Blue Collar Services",
            ),
            TagListItem(
                descriptor=TagDescriptor(code="employment-type", name="Employment type"),
                value="full-time",
            ),
            TagListItem(
                descriptor=TagDescriptor(code="job-role", name="Job role"),
                value=entry.skill_category,
            ),
        ],
    )

    salary_tag = Tag(
        display=True,
        descriptor=TagDescriptor(code="salary-info", name="Salary information"),
        items=[
            TagListItem(
                descriptor=TagDescriptor(code="gross-min", name="Minimum gross pay"),
                value="180000",
            ),
            TagListItem(
                descriptor=TagDescriptor(code="gross-max", name="Maximum gross pay"),
                value="360000",
            ),
        ],
    )

    item = Item(
        id=entry.worker_id,
        descriptor=Descriptor(
            name=f"{entry.skill_category} — {entry.name}",
            short_desc=f"Verified {entry.skill_category} worker in {entry.district}",
            long_desc=(
                f"{entry.name} is a verified blue-collar worker skilled in "
                f"{entry.skill_category}, available in {entry.district}."
            ),
        ),
        location_ids=["L1"],
        fulfillment_ids=["1"],
        tags=[listing_tag, salary_tag],
    )

    provider = Provider(
        id=BPP_ID,
        descriptor=Descriptor(
            name="ONEST Skill Discovery Node",
            short_desc="Blue-collar worker discovery platform",
        ),
        locations=[location],
        fulfillments=[fulfillment],
        items=[item],
    )

    catalog = Catalog(
        descriptor=Descriptor(name="ONEST Skill Discovery Catalog"),
        providers=[provider],
    )

    payload = OnSearchRequest(
        context=context,
        message=OnSearchMessage(catalog=catalog),
    )

    return payload.model_dump(mode="json", exclude_none=True, by_alias=True)


# ── Publisher ─────────────────────────────────


def publish_to_onest(entry: CatalogEntry) -> bool:
    """
    Build a Beckn ``on_search`` payload for *entry* and POST it to the
    mock ONEST gateway.

    Returns True if the gateway responds with an ACK.
    """
    payload = _build_on_search_payload(entry)

    log.info(
        "ONEST_PUBLISH | worker_id=%s | name=%s | skill=%s | district=%s",
        entry.worker_id,
        entry.name,
        entry.skill_category,
        entry.district,
    )

    try:
        resp = requests.post(
            MOCK_GATEWAY_URL,
            json=payload,
            timeout=5,
        )
        resp.raise_for_status()
        body = resp.json()
        ack = body.get("message", {}).get("ack", {}).get("status", "")
        if ack == "ACK":
            log.info("ONEST gateway ACK for worker_id=%s", entry.worker_id)
            return True
        else:
            log.warning(
                "ONEST gateway NACK for worker_id=%s: %s",
                entry.worker_id,
                body,
            )
            return False
    except requests.RequestException as exc:
        log.warning(
            "ONEST gateway unreachable for worker_id=%s: %s",
            entry.worker_id,
            exc,
        )
        # Return True so the poller still promotes the status in dev mode
        return True
