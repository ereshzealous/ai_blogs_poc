"""The entities of the store. Every field here is part of the data contract (DATA-CONTRACT.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class Customer:
    customer_id: str
    email: str
    email_verified: bool
    messaging_number: str
    region: str
    since: date
    name: str | None = None  # the personas are unnamed: "the customer"


@dataclass(frozen=True)
class Address:
    address_id: str
    customer_id: str
    line1: str
    city: str
    postcode: str
    country: str
    current: bool
    valid_from: date
    valid_to: date | None = None


@dataclass(frozen=True)
class Order:
    order_id: str
    customer_id: str
    placed_at: datetime
    status: str
    region: str
    total: float
    currency: str
    shipping_address_id: str
    delivery_option: str


@dataclass(frozen=True)
class OrderLine:
    line_id: str
    order_id: str
    sku: str
    title: str
    quantity: int
    unit_price: float
    gift: bool
    promised_date: date


@dataclass(frozen=True)
class Payment:
    payment_id: str
    order_id: str
    method_id: str
    method_label: str
    authorized: float
    currency: str


@dataclass(frozen=True)
class Capture:
    capture_id: str
    payment_id: str
    order_id: str
    amount: float
    at: datetime
    method_id: str
    idempotency_key: str


@dataclass(frozen=True)
class Refund:
    refund_id: str
    payment_id: str
    order_id: str
    amount: float
    at: datetime
    method_id: str
    idempotency_key: str
    actor: str


@dataclass(frozen=True)
class Carrier:
    code: str
    name: str
    regions: tuple[str, ...]
    cutoff_hour: int
    working_days: tuple[int, ...]


@dataclass(frozen=True)
class DeliveryOption:
    code: str
    price: float
    upgrade_cost: float
    arrives_on: date
    cutoff_at: datetime


@dataclass(frozen=True)
class Shipment:
    shipment_id: str
    order_id: str
    carrier: str
    tracking: str
    state: str = "not_dispatched"
    redirected: bool = False


@dataclass(frozen=True)
class Stock:
    sku: str
    region: str
    available: int
    reserved: int
    warehouse: str


@dataclass(frozen=True)
class Return:
    rma_id: str
    order_id: str
    line_id: str
    reason: str
    state: str


@dataclass(frozen=True)
class Voucher:
    voucher_id: str
    value: float
    expires_on: date
    constraints: str


@dataclass(frozen=True)
class StoreCredit:
    credit_id: str
    customer_id: str
    value: float
    issued_at: datetime
    reason: str


@dataclass(frozen=True)
class Reply:
    at: datetime
    channel: str  # case | email | sms | messaging
    text: str
    actor: str


@dataclass(frozen=True)
class Case:
    case_id: str
    order_id: str
    customer_id: str
    status: str
    opened_at: datetime
    assigned_to: str
    subject: str
    replies: tuple[Reply, ...] = ()


@dataclass(frozen=True)
class Staff:
    staff_id: str
    role: str
    region: str
    refund_limit: float
    compensation_limit: float
    supervisor_id: str | None
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class Product:
    sku: str
    title: str
    price: float


@dataclass(frozen=True)
class IncidentNote:
    """Why the double charge happened. The incident itself belongs to another note."""

    at: datetime
    reference: str
    summary: str


@dataclass(frozen=True)
class Policy:
    name: str
    version: int
    rules: dict[str, bool] = field(default_factory=dict)
    values: dict[str, float] = field(default_factory=dict)

    def rule(self, key: str) -> bool:
        if key not in self.rules:
            raise KeyError(f"{self.name} policy v{self.version} has no rule {key!r}")
        return self.rules[key]

    def value(self, key: str) -> float:
        if key not in self.values:
            raise KeyError(f"{self.name} policy v{self.version} has no value {key!r}")
        return self.values[key]

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "rules": self.rules, "values": self.values}
