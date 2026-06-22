from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import AuthenticatedUser, get_current_user
from app.schemas.billing import BillingPlan, UsageSummary
from app.services.billing_service import billing_service
from app.services.entitlements import plan_definitions

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=list[BillingPlan])
async def list_plans(settings: Settings = Depends(get_settings)) -> list[BillingPlan]:
    plans = plan_definitions(settings)
    return [
        BillingPlan(
            id="basic",
            name=plans["basic"].name,
            price=0,
            currency="CNY",
            token_limit=0,
            request_limit=plans["basic"].monthly_quota,
            period="month",
            features=list(plans["basic"].features),
        ),
        BillingPlan(
            id="pro",
            name=plans["pro"].name,
            price=59,
            currency="CNY",
            token_limit=None,
            request_limit=plans["pro"].monthly_quota,
            period="month",
            features=list(plans["pro"].features),
        ),
        BillingPlan(
            id="max",
            name=plans["max"].name,
            price=99,
            currency="CNY",
            token_limit=None,
            request_limit=plans["max"].monthly_quota,
            period="month",
            features=list(plans["max"].features),
        ),
    ]


@router.get("/usage", response_model=UsageSummary)
async def usage(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UsageSummary:
    return await billing_service.get_usage(session, user.id)


@router.post("/topup")
async def topup(_user: AuthenticatedUser = Depends(get_current_user)) -> None:
    raise AppError(501, "billing_not_connected", "Payment provider is not connected yet.")


@router.post("/subscribe")
async def subscribe(_user: AuthenticatedUser = Depends(get_current_user)) -> None:
    raise AppError(501, "billing_not_connected", "Payment provider is not connected yet.")


@router.get("/orders/{order_id}")
async def get_order(order_id: str, _user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, str]:
    raise AppError(404, "order_not_found", f"Order not found: {order_id}")


@router.post("/sync")
async def sync_billing(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    return await billing_service.sync(session, user.id)
