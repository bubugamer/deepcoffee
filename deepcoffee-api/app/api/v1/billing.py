from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import AuthenticatedUser, get_current_user
from app.schemas.billing import (
    AlipayOrderResponse,
    BillingCheckoutRequest,
    BillingOrderStatus,
    BillingPlan,
    BillingStatus,
    StripeCheckoutResponse,
    UsageSummary,
)
from app.services.billing_service import billing_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=list[BillingPlan])
async def list_plans(settings: Settings = Depends(get_settings)) -> list[BillingPlan]:
    return billing_service.list_plans(settings)


@router.get("/usage", response_model=UsageSummary)
async def usage(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UsageSummary:
    return await billing_service.get_usage(session, user.id)


@router.get("/status", response_model=BillingStatus)
async def billing_status(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BillingStatus:
    return await billing_service.status(session, user.id)


@router.post("/alipay/orders", response_model=AlipayOrderResponse)
async def create_alipay_order(
    payload: BillingCheckoutRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AlipayOrderResponse:
    return await billing_service.create_alipay_order(
        session,
        user_id=user.id,
        email=user.email,
        plan=payload.plan,
        interval=payload.interval,
        settings=settings,
    )


@router.post("/alipay/notify", response_class=PlainTextResponse)
async def alipay_notify(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    raw_body = await request.body()
    try:
        await billing_service.handle_alipay_notify(session, raw_body, settings)
    except Exception as exc:  # noqa: BLE001 - provider expects plain "failure"
        logger.exception("Alipay notification failed: %s", exc)
        return PlainTextResponse("failure")
    return PlainTextResponse("success")


@router.post("/alipay/orders/{order_id}/query", response_model=BillingOrderStatus)
async def query_alipay_order(
    order_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> BillingOrderStatus:
    return await billing_service.query_alipay_order(session, user.id, order_id, settings)


@router.post("/stripe/checkout", response_model=StripeCheckoutResponse)
async def create_stripe_checkout(
    payload: BillingCheckoutRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> StripeCheckoutResponse:
    return await billing_service.create_stripe_checkout(
        session,
        user_id=user.id,
        email=user.email,
        plan=payload.plan,
        interval=payload.interval,
        settings=settings,
    )


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    await billing_service.handle_stripe_webhook(session, payload, signature, settings)
    return {"received": True}


@router.get("/orders/{order_id}", response_model=BillingOrderStatus)
async def get_order(
    order_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BillingOrderStatus:
    return await billing_service.get_order(session, user.id, order_id)


@router.post("/topup")
async def topup(_user: AuthenticatedUser = Depends(get_current_user)) -> None:
    raise AppError(410, "billing_topup_removed", "Top-up is no longer supported.")


@router.post("/subscribe")
async def subscribe(_user: AuthenticatedUser = Depends(get_current_user)) -> None:
    raise AppError(410, "billing_subscribe_replaced", "Use /billing/stripe/checkout instead.")


@router.post("/sync")
async def sync_billing(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    return await billing_service.sync(session, user.id)
