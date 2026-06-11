"""Billing compatibility service.

DeepCoffee now owns AI quota and usage internally. Payment endpoints still exist
as placeholders, while usage reads the current-month DeepCoffee AI counters.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.usage import ai_usage_repository
from app.schemas.billing import UsageSummary


class BillingService:
    async def get_usage(self, session: AsyncSession, user_id: str) -> UsageSummary:
        return UsageSummary(
            total_tokens=0,
            total_requests=await ai_usage_repository.effective_count_for(session, user_id),
            total_cost=0,
            by_model=[],
        )

    async def sync(self, session: AsyncSession, user_id: str) -> dict[str, str]:  # noqa: ARG002
        return {"status": "skipped", "reason": "usage is managed by DeepCoffee"}


billing_service = BillingService()
