"""
Pydantic models mirroring the Beckn / DSEP / ONEST protocol schema.

Covers the **full** transaction lifecycle for the ``onest:work-opportunities``
domain: search, select, init, confirm, status, update, cancel and all their
``on_*`` callbacks, plus the registry subscribe/on_subscribe handshake.

Reference:
  • DSEP spec   – github.com/beckn/DSEP-Specification
  • ONEST spec  – github.com/ONEST-Network/ONEST-Specification
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════
#  Primitives
# ═══════════════════════════════════════════════


class Descriptor(BaseModel):
    name: str
    code: Optional[str] = None
    short_desc: Optional[str] = None
    long_desc: Optional[str] = None
    images: Optional[list[dict[str, str]]] = None
    media: Optional[list[dict[str, str]]] = None


class TagDescriptor(BaseModel):
    code: str
    name: Optional[str] = None


class TagListItem(BaseModel):
    descriptor: TagDescriptor
    value: str
    display: bool = True


class Tag(BaseModel):
    display: bool = True
    descriptor: TagDescriptor
    items: list[TagListItem] = Field(default_factory=list, alias="list")

    model_config = {"populate_by_name": True}


class City(BaseModel):
    name: str
    code: Optional[str] = None


class State(BaseModel):
    name: str
    code: Optional[str] = None


class Country(BaseModel):
    name: str = "India"
    code: str = "IN"


class Address(BaseModel):
    door: Optional[str] = None
    building: Optional[str] = None
    street: Optional[str] = None
    locality: Optional[str] = None
    ward: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    area_code: Optional[str] = None  # PIN / ZIP code


class Location(BaseModel):
    id: str
    city: Optional[City] = None
    state: Optional[State] = None
    country: Optional[Country] = None
    address: Optional[Address] = None
    area_code: Optional[str] = None  # PIN / ZIP code
    gps: Optional[str] = None  # "lat,lon"


class ItemQuantity(BaseModel):
    available: Optional[dict[str, int]] = None  # {"count": N}


class TimeRange(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None


class Time(BaseModel):
    range: Optional[TimeRange] = None


class Person(BaseModel):
    name: Optional[str] = None
    image: Optional[str] = None
    dob: Optional[str] = None  # YYYY-MM-DD
    gender: Optional[str] = None
    age: Optional[str] = None
    skills: Optional[list[dict[str, str]]] = None
    languages: Optional[list[dict[str, str]]] = None
    tags: Optional[list[Tag]] = None
    cred: Optional[str] = None


class Contact(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None


class Customer(BaseModel):
    person: Optional[Person] = None
    contact: Optional[Contact] = None


class FulfillmentState(BaseModel):
    descriptor: Optional[Descriptor] = None
    updated_at: Optional[str] = None


# ═══════════════════════════════════════════════
#  Mid-level objects
# ═══════════════════════════════════════════════


class Fulfillment(BaseModel):
    id: str
    type: Optional[str] = None  # REMOTE / HYBRID / ONSITE
    state: Optional[FulfillmentState] = None
    customer: Optional[Customer] = None
    tags: Optional[list[Tag]] = None


class XInputFormHead(BaseModel):
    descriptor: Optional[Descriptor] = None
    index: Optional[dict[str, int]] = None  # {"min": 0, "cur": 0, "max": 1}
    headings: Optional[list[str]] = None


class XInputForm(BaseModel):
    mime_type: Optional[str] = None
    url: Optional[str] = None
    resubmit: bool = False


class XInput(BaseModel):
    required: bool = False
    head: Optional[XInputFormHead] = None
    form: Optional[XInputForm] = None


class Item(BaseModel):
    id: str
    descriptor: Optional[Descriptor] = None
    quantity: Optional[ItemQuantity] = None
    location_ids: Optional[list[str]] = None
    fulfillment_ids: Optional[list[str]] = None
    time: Optional[Time] = None
    tags: Optional[list[Tag]] = None
    xinput: Optional[XInput] = None


class Provider(BaseModel):
    id: str
    descriptor: Optional[Descriptor] = None
    locations: Optional[list[Location]] = None
    fulfillments: Optional[list[Fulfillment]] = None
    items: Optional[list[Item]] = None


class Billing(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    tax_number: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class Quotation(BaseModel):
    price: Optional[dict[str, str]] = None
    breakup: Optional[list[dict[str, Any]]] = None
    ttl: Optional[str] = None


class Payment(BaseModel):
    uri: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    params: Optional[dict[str, Any]] = None
    time: Optional[Time] = None


class Document(BaseModel):
    url: Optional[str] = None
    label: Optional[str] = None


class Cancellation(BaseModel):
    cancelled_by: Optional[str] = None
    reason: Optional[Descriptor] = None


# ═══════════════════════════════════════════════
#  Order
# ═══════════════════════════════════════════════


class Order(BaseModel):
    id: Optional[str] = None
    state: Optional[str] = None
    provider: Optional[Provider] = None
    items: Optional[list[Item]] = None
    fulfillments: Optional[list[Fulfillment]] = None
    billing: Optional[Billing] = None
    quote: Optional[Quotation] = None
    payment: Optional[Payment] = None
    documents: Optional[list[Document]] = None
    cancellation: Optional[Cancellation] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ═══════════════════════════════════════════════
#  Catalog
# ═══════════════════════════════════════════════


class Catalog(BaseModel):
    descriptor: Optional[Descriptor] = None
    providers: list[Provider] = Field(default_factory=list)


# ═══════════════════════════════════════════════
#  Context
# ═══════════════════════════════════════════════


class Context(BaseModel):
    domain: str = "onest:work-opportunities"
    action: str = "on_search"
    version: str = "1.1.0"
    bap_id: Optional[str] = None
    bap_uri: Optional[str] = None
    bpp_id: Optional[str] = None
    bpp_uri: Optional[str] = None
    transaction_id: Optional[str] = None
    message_id: Optional[str] = None
    timestamp: Optional[str] = None
    ttl: str = "P1M"


# ═══════════════════════════════════════════════
#  Ack / Error
# ═══════════════════════════════════════════════


class Ack(BaseModel):
    status: str = "ACK"


class AckMessage(BaseModel):
    ack: Ack = Field(default_factory=Ack)


class BecknError(BaseModel):
    type: Optional[str] = None
    code: Optional[str] = None
    path: Optional[str] = None
    message: Optional[str] = None


class BecknAckResponse(BaseModel):
    """Standard Beckn ACK/NACK returned to every incoming request."""
    message: AckMessage = Field(default_factory=AckMessage)
    error: Optional[BecknError] = None


# ═══════════════════════════════════════════════
#  ONEST Error Codes (subset)
# ═══════════════════════════════════════════════

BECKN_ERRORS: dict[str, tuple[str, str]] = {
    "10000": ("CONTEXT-ERROR", "Invalid Context"),
    "10001": ("CONTEXT-ERROR", "Invalid domain"),
    "20000": ("CORE-ERROR", "Internal Server Error"),
    "30000": ("DOMAIN-ERROR", "Provider not found"),
    "30001": ("DOMAIN-ERROR", "Provider location not found"),
    "30004": ("DOMAIN-ERROR", "Item not found"),
    "30009": ("DOMAIN-ERROR", "Fulfillment agent not available"),
    "40000": ("POLICY-ERROR", "Business policy error"),
    "40001": ("POLICY-ERROR", "Action not applicable"),
    "40002": ("POLICY-ERROR", "Order not found"),
    "40003": ("POLICY-ERROR", "Order cannot be updated"),
    "40004": ("POLICY-ERROR", "Order cannot be cancelled"),
    "50000": ("JSON-SCHEMA-ERROR", "Invalid JSON"),
    "50001": ("JSON-SCHEMA-ERROR", "Missing required fields"),
}


def make_error(code: str, custom_message: str | None = None) -> BecknError:
    err_type, default_msg = BECKN_ERRORS.get(code, ("CORE-ERROR", "Unknown error"))
    return BecknError(type=err_type, code=code, message=custom_message or default_msg)


def nack_response(code: str, custom_message: str | None = None) -> BecknAckResponse:
    return BecknAckResponse(
        message=AckMessage(ack=Ack(status="NACK")),
        error=make_error(code, custom_message),
    )


def ack_response() -> BecknAckResponse:
    return BecknAckResponse(message=AckMessage(ack=Ack(status="ACK")))


# ═══════════════════════════════════════════════
#  Search / on_search
# ═══════════════════════════════════════════════


class SearchIntent(BaseModel):
    descriptor: Optional[Descriptor] = None
    provider: Optional[Provider] = None
    fulfillment: Optional[Fulfillment] = None
    item: Optional[Item] = None
    category: Optional[dict[str, Any]] = None
    tags: Optional[list[Tag]] = None


class SearchMessage(BaseModel):
    intent: Optional[SearchIntent] = None


class SearchRequest(BaseModel):
    context: Context
    message: SearchMessage


class OnSearchMessage(BaseModel):
    catalog: Catalog


class OnSearchRequest(BaseModel):
    context: Context
    message: OnSearchMessage


# backward-compat alias
OnSearchAckResponse = BecknAckResponse


# ═══════════════════════════════════════════════
#  Select / on_select
# ═══════════════════════════════════════════════


class SelectMessage(BaseModel):
    order: Order


class SelectRequest(BaseModel):
    context: Context
    message: SelectMessage


class OnSelectMessage(BaseModel):
    order: Order


class OnSelectRequest(BaseModel):
    context: Context
    message: OnSelectMessage


# ═══════════════════════════════════════════════
#  Init / on_init
# ═══════════════════════════════════════════════


class InitMessage(BaseModel):
    order: Order


class InitRequest(BaseModel):
    context: Context
    message: InitMessage


class OnInitMessage(BaseModel):
    order: Order


class OnInitRequest(BaseModel):
    context: Context
    message: OnInitMessage


# ═══════════════════════════════════════════════
#  Confirm / on_confirm
# ═══════════════════════════════════════════════


class ConfirmMessage(BaseModel):
    order: Order


class ConfirmRequest(BaseModel):
    context: Context
    message: ConfirmMessage


class OnConfirmMessage(BaseModel):
    order: Order


class OnConfirmRequest(BaseModel):
    context: Context
    message: OnConfirmMessage


# ═══════════════════════════════════════════════
#  Status / on_status
# ═══════════════════════════════════════════════


class StatusMessage(BaseModel):
    order: Order


class StatusRequest(BaseModel):
    context: Context
    message: StatusMessage


class OnStatusMessage(BaseModel):
    order: Order


class OnStatusRequest(BaseModel):
    context: Context
    message: OnStatusMessage


# ═══════════════════════════════════════════════
#  Update / on_update
# ═══════════════════════════════════════════════


class UpdateMessage(BaseModel):
    update_target: Optional[str] = None
    order: Order


class UpdateRequest(BaseModel):
    context: Context
    message: UpdateMessage


class OnUpdateMessage(BaseModel):
    order: Order


class OnUpdateRequest(BaseModel):
    context: Context
    message: OnUpdateMessage


# ═══════════════════════════════════════════════
#  Cancel / on_cancel
# ═══════════════════════════════════════════════


class CancelMessage(BaseModel):
    order: Order


class CancelRequest(BaseModel):
    context: Context
    message: CancelMessage


class OnCancelMessage(BaseModel):
    order: Order


class OnCancelRequest(BaseModel):
    context: Context
    message: OnCancelMessage


# ═══════════════════════════════════════════════
#  Registry Subscribe / on_subscribe
# ═══════════════════════════════════════════════


class SubscriberInfo(BaseModel):
    subscriber_id: str
    type: str = "bpp"
    cb_url: str
    domain: str = "onest:work-opportunities"
    city: Optional[str] = None
    country: str = "IND"
    signing_public_key: str
    encryption_public_key: str
    status: str = "INITIATED"
    created: Optional[str] = None
    updated: Optional[str] = None
    expires: Optional[str] = None


class SubscribeRequest(BaseModel):
    context: Optional[Context] = None
    message: Optional[SubscriberInfo] = None


class OnSubscribeRequest(BaseModel):
    subscriber_id: str
    challenge: Optional[str] = None
