from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

BillingPlanId = Literal["basic", "pro", "max"]
PaidPlanId = Literal["pro", "max"]
BillingInterval = Literal["monthly", "yearly"]
BillingProvider = Literal["alipay", "stripe"]


class BillingPlanPrice(BaseModel):
    amount: float
    currency: str
    interval: BillingInterval
    display: str


class BillingPlan(BaseModel):
    id: str
    name: str
    price: float
    currency: str
    token_limit: int | None
    request_limit: int | None
    period: str
    features: list[str]
    prices: dict[str, BillingPlanPrice] = {}


class BillingCheckoutRequest(BaseModel):
    plan: PaidPlanId
    interval: BillingInterval


class AlipayOrderResponse(BaseModel):
    id: str
    provider: Literal["alipay"]
    plan: PaidPlanId
    interval: BillingInterval
    amount: float
    currency: str
    status: str
    qr_code: str
    expires_at: datetime


class StripeCheckoutResponse(BaseModel):
    id: str
    provider: Literal["stripe"]
    plan: PaidPlanId
    interval: BillingInterval
    status: str
    checkout_url: str


class BillingOrderStatus(BaseModel):
    id: str
    provider: BillingProvider
    plan: str
    interval: str
    amount: float
    currency: str
    status: str
    qr_code: str | None = None
    checkout_url: str | None = None
    expires_at: datetime | None = None
    paid_at: datetime | None = None
    period_end: datetime | None = None


class BillingStatus(BaseModel):
    plan: str
    plan_source: str
    plan_expires_at: datetime | None = None
    active_subscription_status: str | None = None
    active_subscription_interval: str | None = None
    active_subscription_provider: str | None = None
    active_subscription_renews_at: datetime | None = None


class AdminPaymentOrderInfo(BaseModel):
    id: str
    user_id: str
    user_email: str | None = None
    provider: str
    plan: str
    interval: str
    amount: float
    currency: str
    status: str
    external_order_id: str | None = None
    external_transaction_id: str | None = None
    external_subscription_id: str | None = None
    period_end: datetime | None = None
    expires_at: datetime | None = None
    paid_at: datetime | None = None
    created_at: datetime


class UsageSummary(BaseModel):
    total_tokens: int
    total_requests: int
    total_cost: float
    by_model: list[dict[str, int | float | str]]
