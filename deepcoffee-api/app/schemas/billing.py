from __future__ import annotations

from pydantic import BaseModel


class BillingPlan(BaseModel):
    id: str
    name: str
    price: float
    currency: str
    token_limit: int | None
    request_limit: int | None
    period: str
    features: list[str]


class UsageSummary(BaseModel):
    total_tokens: int
    total_requests: int
    total_cost: float
    by_model: list[dict[str, int | float | str]]
