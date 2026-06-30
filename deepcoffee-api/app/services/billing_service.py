"""Billing and payment service.

DeepCoffee still owns the membership entitlement (`user_profiles.plan`). Payment
providers only create and update payment records; successful records activate
the existing plan field plus an optional expiry timestamp.
"""

from __future__ import annotations

import base64
import calendar
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.tables import BillingPaymentOrder, BillingProviderEvent, BillingSubscription, UserProfile
from app.repositories.usage import ai_usage_repository
from app.schemas.billing import (
    AdminPaymentOrderInfo,
    AlipayOrderResponse,
    BillingOrderStatus,
    BillingPlan,
    BillingPlanPrice,
    BillingStatus,
    StripeCheckoutResponse,
    UsageSummary,
)
from app.services.entitlements import PLAN_BASIC, PLAN_MAX, PLAN_PRO, normalize_plan, plan_definitions

logger = logging.getLogger(__name__)

PLAN_PRICES_CNY: dict[tuple[str, str], int] = {
    (PLAN_PRO, "monthly"): 5900,
    (PLAN_PRO, "yearly"): 56800,
    (PLAN_MAX, "monthly"): 9900,
    (PLAN_MAX, "yearly"): 93800,
}
VALID_PAID_PLANS = {PLAN_PRO, PLAN_MAX}
VALID_INTERVALS = {"monthly", "yearly"}
ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing", "past_due"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _money(cents: int) -> float:
    return float(Decimal(cents) / Decimal(100))


def _format_amount(cents: int) -> str:
    return f"{_money(cents):.2f}"


def _add_interval(start: datetime, interval: str) -> datetime:
    if interval == "yearly":
        try:
            return start.replace(year=start.year + 1)
        except ValueError:
            return start.replace(year=start.year + 1, day=28)
    month = start.month + 1
    year = start.year
    if month > 12:
        month = 1
        year += 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


def _add_months(start: datetime, months: int) -> datetime:
    """在 start 上加 N 个自然月，跨年进位，目标月没有该日则夹到月末（如 1/31 + 1 月 → 2/28）。"""
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


def _validate_paid_plan(plan: str, interval: str) -> tuple[str, str]:
    normalized = normalize_plan(plan)
    if normalized not in VALID_PAID_PLANS:
        raise AppError(400, "invalid_plan", "请选择 Pro 或 Max。")
    if interval not in VALID_INTERVALS:
        raise AppError(400, "invalid_interval", "请选择月付或年付。")
    return normalized, interval


def _plan_title(plan: str, interval: str) -> str:
    plan_name = "Pro" if plan == PLAN_PRO else "Max"
    interval_name = "月付" if interval == "monthly" else "年付"
    return f"DeepCoffee {plan_name} {interval_name}"


def _normalize_pem(raw: str, kind: str) -> bytes:
    stripped = raw.strip().replace("\\n", "\n")
    if "BEGIN" in stripped:
        return stripped.encode()
    label = "PRIVATE KEY" if kind == "private" else "PUBLIC KEY"
    body = "\n".join(stripped[i : i + 64] for i in range(0, len(stripped), 64))
    return f"-----BEGIN {label}-----\n{body}\n-----END {label}-----\n".encode()


def _to_order_status(row: BillingPaymentOrder) -> BillingOrderStatus:
    return BillingOrderStatus(
        id=row.id,
        provider=row.provider,  # type: ignore[arg-type]
        plan=row.plan,
        interval=row.interval,
        amount=_money(row.amount_cents),
        currency=row.currency,
        status=row.status,
        qr_code=row.qr_code,
        checkout_url=row.checkout_url,
        expires_at=row.expires_at,
        paid_at=row.paid_at,
        period_end=row.period_end,
    )


class BillingService:
    def list_plans(self, settings: Settings) -> list[BillingPlan]:
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
                prices={},
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
                prices={
                    "monthly": BillingPlanPrice(amount=59, currency="CNY", interval="monthly", display="59 元/月"),
                    "yearly": BillingPlanPrice(amount=568, currency="CNY", interval="yearly", display="568 元/年"),
                },
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
                prices={
                    "monthly": BillingPlanPrice(amount=99, currency="CNY", interval="monthly", display="99 元/月"),
                    "yearly": BillingPlanPrice(amount=938, currency="CNY", interval="yearly", display="938 元/年"),
                },
            ),
        ]

    async def get_usage(self, session: AsyncSession, user_id: str) -> UsageSummary:
        return UsageSummary(
            total_tokens=0,
            total_requests=await ai_usage_repository.effective_count_for(session, user_id),
            total_cost=0,
            by_model=[],
        )

    async def sync_expired_membership(self, session: AsyncSession, user_id: str) -> None:
        profile = await session.get(UserProfile, user_id)
        if profile is None:
            return
        expires_at = profile.plan_expires_at
        if profile.plan == PLAN_BASIC or profile.plan_source == "manual" or expires_at is None:
            return
        if expires_at <= _now():
            profile.plan = PLAN_BASIC
            profile.plan_source = "expired"
            profile.plan_expires_at = None
            await session.flush()

    async def status(self, session: AsyncSession, user_id: str) -> BillingStatus:
        await self.sync_expired_membership(session, user_id)
        profile = await session.get(UserProfile, user_id)
        if profile is None:
            raise AppError(404, "user_not_found", "User profile not found.")
        subscription = await session.scalar(
            select(BillingSubscription)
            .where(BillingSubscription.user_id == user_id)
            .order_by(desc(BillingSubscription.updated_at))
            .limit(1)
        )
        return BillingStatus(
            plan=normalize_plan(profile.plan),
            plan_source=profile.plan_source,
            plan_expires_at=profile.plan_expires_at,
            active_subscription_status=subscription.status if subscription else None,
            active_subscription_interval=subscription.interval if subscription else None,
            active_subscription_provider=subscription.provider if subscription else None,
            active_subscription_renews_at=subscription.current_period_end if subscription else None,
        )

    async def create_alipay_order(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        email: str | None,
        plan: str,
        interval: str,
        settings: Settings,
    ) -> AlipayOrderResponse:
        plan, interval = _validate_paid_plan(plan, interval)
        self._require_alipay(settings)
        await self._ensure_profile(session, user_id, email)
        order_id = f"dc_{uuid.uuid4().hex}"
        amount_cents = PLAN_PRICES_CNY[(plan, interval)]
        expires_at = _now() + timedelta(minutes=settings.alipay_order_ttl_minutes)
        row = BillingPaymentOrder(
            id=order_id,
            user_id=user_id,
            provider="alipay",
            plan=plan,
            interval=interval,
            amount_cents=amount_cents,
            currency="CNY",
            status="pending",
            external_order_id=order_id,
            expires_at=expires_at,
        )
        session.add(row)
        await session.flush()

        result = await self._alipay_precreate(
            settings,
            out_trade_no=order_id,
            subject=_plan_title(plan, interval),
            total_amount=_format_amount(amount_cents),
            timeout_express=f"{settings.alipay_order_ttl_minutes}m",
        )
        qr_code = str(result.get("qr_code") or "")
        if not qr_code:
            raise AppError(502, "alipay_qr_missing", "支付宝未返回可用二维码。")
        row.qr_code = qr_code
        row.provider_payload = result
        await session.flush()
        return AlipayOrderResponse(
            id=row.id,
            provider="alipay",
            plan=plan,  # type: ignore[arg-type]
            interval=interval,  # type: ignore[arg-type]
            amount=_money(row.amount_cents),
            currency=row.currency,
            status=row.status,
            qr_code=qr_code,
            expires_at=expires_at,
        )

    async def get_order(self, session: AsyncSession, user_id: str, order_id: str) -> BillingOrderStatus:
        await self.sync_expired_membership(session, user_id)
        row = await session.get(BillingPaymentOrder, order_id)
        if row is None or row.user_id != user_id:
            raise AppError(404, "order_not_found", "Order not found.")
        await self._expire_order_if_needed(session, row)
        return _to_order_status(row)

    async def handle_alipay_notify(self, session: AsyncSession, raw_body: bytes, settings: Settings) -> None:
        data = {key: values[-1] for key, values in parse_qs(raw_body.decode("utf-8"), keep_blank_values=True).items()}
        if not data:
            raise AppError(400, "empty_notify", "Empty Alipay notification.")
        if not self._verify_alipay_signature(settings, data):
            raise AppError(400, "invalid_alipay_signature", "Invalid Alipay signature.")

        trade_status = data.get("trade_status")
        if trade_status not in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
            return
        out_trade_no = data.get("out_trade_no")
        if not out_trade_no:
            raise AppError(400, "missing_order", "Missing Alipay order number.")
        row = await session.scalar(
            select(BillingPaymentOrder).where(
                BillingPaymentOrder.provider == "alipay",
                BillingPaymentOrder.external_order_id == out_trade_no,
            )
        )
        if row is None:
            raise AppError(404, "order_not_found", "Order not found.")
        if settings.alipay_app_id and data.get("app_id") and data.get("app_id") != settings.alipay_app_id:
            raise AppError(400, "alipay_app_mismatch", "Alipay app_id mismatch.")
        if settings.alipay_seller_id and data.get("seller_id") and data.get("seller_id") != settings.alipay_seller_id:
            raise AppError(400, "alipay_seller_mismatch", "Alipay seller_id mismatch.")
        paid_cents = int((Decimal(data.get("total_amount", "0")) * Decimal(100)).quantize(Decimal("1")))
        if paid_cents != row.amount_cents:
            raise AppError(400, "amount_mismatch", "Alipay amount mismatch.")
        await self._mark_order_paid(
            session,
            row,
            transaction_id=data.get("trade_no"),
            provider_payload={**row.provider_payload, "notify": data},
        )

    async def query_alipay_order(self, session: AsyncSession, user_id: str, order_id: str, settings: Settings) -> BillingOrderStatus:
        self._require_alipay(settings)
        row = await session.get(BillingPaymentOrder, order_id)
        if row is None or row.user_id != user_id or row.provider != "alipay":
            raise AppError(404, "order_not_found", "Order not found.")
        if row.status == "paid":
            return _to_order_status(row)
        await self._expire_order_if_needed(session, row)
        if row.status != "pending":
            return _to_order_status(row)
        result = await self._alipay_query(settings, out_trade_no=row.external_order_id or row.id)
        trade_status = result.get("trade_status")
        if trade_status in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
            await self._mark_order_paid(
                session,
                row,
                transaction_id=result.get("trade_no"),
                provider_payload={**row.provider_payload, "query": result},
            )
        return _to_order_status(row)

    async def create_stripe_checkout(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        email: str | None,
        plan: str,
        interval: str,
        settings: Settings,
    ) -> StripeCheckoutResponse:
        plan, interval = _validate_paid_plan(plan, interval)
        price_id = self._stripe_price_id(settings, plan, interval)
        if not settings.stripe_secret_key or not price_id:
            raise AppError(501, "stripe_not_configured", "Stripe payment is not configured yet.")
        await self._ensure_profile(session, user_id, email)
        row = BillingPaymentOrder(
            id=f"st_{uuid.uuid4().hex}",
            user_id=user_id,
            provider="stripe",
            plan=plan,
            interval=interval,
            amount_cents=0,
            currency="HKD",
            status="pending",
        )
        session.add(row)
        await session.flush()
        success_url = f"{settings.frontend_public_url.rstrip('/')}/app/billing/success?provider=stripe&order_id={row.id}&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{settings.frontend_public_url.rstrip('/')}/app/settings?tab=plan"
        checkout = await self._stripe_create_checkout_session(
            settings,
            price_id=price_id,
            user_id=user_id,
            email=email,
            plan=plan,
            interval=interval,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        row.external_order_id = checkout["id"]
        row.checkout_url = checkout["url"]
        row.provider_payload = checkout
        await session.flush()
        return StripeCheckoutResponse(
            id=row.id,
            provider="stripe",
            plan=plan,  # type: ignore[arg-type]
            interval=interval,  # type: ignore[arg-type]
            status=row.status,
            checkout_url=row.checkout_url,
        )

    async def handle_stripe_webhook(self, session: AsyncSession, payload: bytes, signature: str | None, settings: Settings) -> None:
        event = self._verify_stripe_event(payload, signature, settings)
        event_id = str(event.get("id") or "")
        if not event_id:
            raise AppError(400, "stripe_event_missing_id", "Stripe event id is missing.")
        existing = await session.scalar(
            select(BillingProviderEvent).where(
                BillingProviderEvent.provider == "stripe",
                BillingProviderEvent.provider_event_id == event_id,
            )
        )
        if existing is not None:
            return
        session.add(
            BillingProviderEvent(
                provider="stripe",
                provider_event_id=event_id,
                event_type=event.get("type"),
                payload=event,
            )
        )
        event_type = event.get("type")
        obj = event.get("data", {}).get("object", {})
        if event_type == "checkout.session.completed":
            await self._handle_stripe_checkout_completed(session, obj)
        elif event_type in {"customer.subscription.created", "customer.subscription.updated"}:
            await self._handle_stripe_subscription_update(session, obj, settings)
        elif event_type == "customer.subscription.deleted":
            await self._handle_stripe_subscription_deleted(session, obj)
        await session.flush()

    async def list_admin_payments(self, session: AsyncSession, *, page: int = 1, page_size: int = 50) -> list[AdminPaymentOrderInfo]:
        offset = (page - 1) * page_size
        result = await session.execute(
            select(BillingPaymentOrder, UserProfile.email)
            .outerjoin(UserProfile, BillingPaymentOrder.user_id == UserProfile.id)
            .order_by(desc(BillingPaymentOrder.created_at))
            .offset(offset)
            .limit(page_size)
        )
        return [
            AdminPaymentOrderInfo(
                id=row.id,
                user_id=row.user_id,
                user_email=email,
                provider=row.provider,
                plan=row.plan,
                interval=row.interval,
                amount=_money(row.amount_cents),
                currency=row.currency,
                status=row.status,
                external_order_id=row.external_order_id,
                external_transaction_id=row.external_transaction_id,
                external_subscription_id=row.external_subscription_id,
                period_end=row.period_end,
                expires_at=row.expires_at,
                paid_at=row.paid_at,
                created_at=row.created_at,
            )
            for row, email in result.all()
        ]

    async def sync(self, session: AsyncSession, user_id: str) -> dict[str, str]:
        await self.sync_expired_membership(session, user_id)
        return {"status": "ok", "reason": "billing status synced"}

    async def _ensure_profile(self, session: AsyncSession, user_id: str, email: str | None) -> UserProfile:
        row = await session.get(UserProfile, user_id)
        if row is None:
            display_name = email.split("@", 1)[0] if email else None
            row = UserProfile(id=user_id, email=email, display_name=display_name)
            session.add(row)
        elif email and row.email != email:
            row.email = email
        await session.flush()
        return row

    async def _expire_order_if_needed(self, session: AsyncSession, row: BillingPaymentOrder) -> None:
        if row.status == "pending" and row.expires_at is not None and row.expires_at <= _now():
            row.status = "expired"
            await session.flush()

    async def _mark_order_paid(
        self,
        session: AsyncSession,
        row: BillingPaymentOrder,
        *,
        transaction_id: str | None,
        provider_payload: dict[str, Any],
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> None:
        if row.status == "paid":
            return
        now = _now()
        period_start = period_start or now
        period_end = period_end or _add_interval(period_start, row.interval)
        row.status = "paid"
        row.external_transaction_id = transaction_id or row.external_transaction_id
        row.provider_payload = provider_payload
        row.paid_at = now
        row.period_start = period_start
        row.period_end = period_end
        await self._activate_membership(session, row.user_id, row.plan, row.provider, period_end)

    async def grant_membership(
        self,
        session: AsyncSession,
        user_id: str,
        *,
        plan: str,
        months: int,
        source: str = "invite",
    ) -> datetime:
        """按「等级 + 月数」开通会员（邀请码赠送等场景复用）。

        plan_source 非 'manual'，故 sync_expired_membership 会在 plan_expires_at 到期后自动回落 basic。
        返回开通到期时间。
        """
        expires_at = _add_months(_now(), max(1, months))
        await self._activate_membership(session, user_id, normalize_plan(plan), source, expires_at)
        return expires_at

    async def _activate_membership(self, session: AsyncSession, user_id: str, plan: str, source: str, expires_at: datetime) -> None:
        profile = await session.get(UserProfile, user_id)
        if profile is None:
            raise AppError(404, "user_not_found", "User profile not found.")
        profile.plan = normalize_plan(plan)
        profile.plan_source = source
        profile.plan_expires_at = expires_at
        await session.flush()

    def _require_alipay(self, settings: Settings) -> None:
        if not (settings.alipay_app_id and settings.alipay_app_private_key and settings.alipay_public_key):
            raise AppError(501, "alipay_not_configured", "Alipay payment is not configured yet.")

    def _alipay_notify_url(self, settings: Settings) -> str:
        if settings.alipay_notify_url:
            return settings.alipay_notify_url
        if settings.backend_public_url:
            return f"{settings.backend_public_url.rstrip('/')}/v1/billing/alipay/notify"
        raise AppError(501, "alipay_notify_not_configured", "Alipay notify URL is not configured.")

    async def _alipay_precreate(
        self,
        settings: Settings,
        *,
        out_trade_no: str,
        subject: str,
        total_amount: str,
        timeout_express: str,
    ) -> dict[str, Any]:
        biz_content: dict[str, Any] = {
            "out_trade_no": out_trade_no,
            "total_amount": total_amount,
            "subject": subject,
            "timeout_express": timeout_express,
        }
        if settings.alipay_seller_id:
            biz_content["seller_id"] = settings.alipay_seller_id
        response = await self._alipay_call(
            settings,
            method="alipay.trade.precreate",
            biz_content=biz_content,
            notify_url=self._alipay_notify_url(settings),
        )
        return response

    async def _alipay_query(self, settings: Settings, *, out_trade_no: str) -> dict[str, Any]:
        return await self._alipay_call(settings, method="alipay.trade.query", biz_content={"out_trade_no": out_trade_no})

    async def _alipay_call(
        self,
        settings: Settings,
        *,
        method: str,
        biz_content: dict[str, Any],
        notify_url: str | None = None,
    ) -> dict[str, Any]:
        self._require_alipay(settings)
        params: dict[str, str] = {
            "app_id": settings.alipay_app_id or "",
            "method": method,
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": _now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "biz_content": json.dumps(biz_content, ensure_ascii=False, separators=(",", ":")),
        }
        if notify_url:
            params["notify_url"] = notify_url
        params["sign"] = self._sign_alipay_params(settings, params)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(settings.alipay_gateway_url, data=params)
        resp.raise_for_status()
        payload = resp.json()
        response_key = method.replace(".", "_") + "_response"
        result = payload.get(response_key)
        if not isinstance(result, dict):
            raise AppError(502, "alipay_bad_response", "支付宝返回格式异常。")
        if result.get("code") != "10000":
            raise AppError(502, "alipay_request_failed", result.get("sub_msg") or result.get("msg") or "支付宝请求失败。")
        return result

    def _sign_alipay_params(self, settings: Settings, params: dict[str, str]) -> str:
        content = "&".join(f"{key}={params[key]}" for key in sorted(params) if key != "sign" and params[key] != "")
        key = serialization.load_pem_private_key(
            _normalize_pem(settings.alipay_app_private_key or "", "private"),
            password=None,
        )
        signature = key.sign(content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(signature).decode("ascii")

    def _verify_alipay_signature(self, settings: Settings, data: dict[str, str]) -> bool:
        self._require_alipay(settings)
        signature = data.get("sign")
        if not signature:
            return False
        content = "&".join(
            f"{key}={data[key]}"
            for key in sorted(data)
            if key not in {"sign", "sign_type"} and data[key] != ""
        )
        public_key = serialization.load_pem_public_key(_normalize_pem(settings.alipay_public_key or "", "public"))
        try:
            public_key.verify(base64.b64decode(signature), content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
            return True
        except (InvalidSignature, ValueError):
            return False

    def _stripe_price_id(self, settings: Settings, plan: str, interval: str) -> str | None:
        return {
            (PLAN_PRO, "monthly"): settings.stripe_price_pro_monthly,
            (PLAN_PRO, "yearly"): settings.stripe_price_pro_yearly,
            (PLAN_MAX, "monthly"): settings.stripe_price_max_monthly,
            (PLAN_MAX, "yearly"): settings.stripe_price_max_yearly,
        }.get((plan, interval))

    def _plan_interval_for_stripe_price(self, settings: Settings, price_id: str | None) -> tuple[str, str] | None:
        for plan in (PLAN_PRO, PLAN_MAX):
            for interval in ("monthly", "yearly"):
                if price_id and self._stripe_price_id(settings, plan, interval) == price_id:
                    return plan, interval
        return None

    async def _stripe_create_checkout_session(
        self,
        settings: Settings,
        *,
        price_id: str,
        user_id: str,
        email: str | None,
        plan: str,
        interval: str,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, Any]:
        data = {
            "mode": "subscription",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": user_id,
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "metadata[user_id]": user_id,
            "metadata[plan]": plan,
            "metadata[interval]": interval,
            "subscription_data[metadata][user_id]": user_id,
            "subscription_data[metadata][plan]": plan,
            "subscription_data[metadata][interval]": interval,
        }
        if email:
            data["customer_email"] = email
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=data,
                headers={"Authorization": f"Bearer {settings.stripe_secret_key}"},
            )
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("id") or not payload.get("url"):
            raise AppError(502, "stripe_bad_response", "Stripe did not return a checkout URL.")
        return payload

    def _verify_stripe_event(self, payload: bytes, signature: str | None, settings: Settings) -> dict[str, Any]:
        if not settings.stripe_webhook_secret:
            raise AppError(501, "stripe_webhook_not_configured", "Stripe webhook is not configured yet.")
        if not signature:
            raise AppError(400, "stripe_signature_missing", "Stripe signature is missing.")
        parts: dict[str, list[str]] = {}
        for item in signature.split(","):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            parts.setdefault(key, []).append(value)
        timestamp = parts.get("t", [""])[0]
        signed_payload = f"{timestamp}.".encode("utf-8") + payload
        expected = hmac.new(settings.stripe_webhook_secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, candidate) for candidate in parts.get("v1", [])):
            raise AppError(400, "stripe_signature_invalid", "Invalid Stripe signature.")
        return json.loads(payload.decode("utf-8"))

    async def _handle_stripe_checkout_completed(self, session: AsyncSession, obj: dict[str, Any]) -> None:
        session_id = obj.get("id")
        row = await session.scalar(
            select(BillingPaymentOrder).where(
                BillingPaymentOrder.provider == "stripe",
                BillingPaymentOrder.external_order_id == session_id,
            )
        )
        if row is None:
            metadata = obj.get("metadata") or {}
            user_id = metadata.get("user_id") or obj.get("client_reference_id")
            plan = normalize_plan(metadata.get("plan"))
            interval = metadata.get("interval")
            if not user_id or plan not in VALID_PAID_PLANS or interval not in VALID_INTERVALS:
                logger.warning("Ignoring checkout.session.completed without usable metadata: %s", session_id)
                return
            row = BillingPaymentOrder(
                id=f"st_{uuid.uuid4().hex}",
                user_id=user_id,
                provider="stripe",
                plan=plan,
                interval=interval,
                amount_cents=0,
                currency=(obj.get("currency") or "hkd").upper(),
                status="pending",
                external_order_id=session_id,
            )
            session.add(row)
        amount_total = obj.get("amount_total")
        if isinstance(amount_total, int):
            row.amount_cents = amount_total
        currency = obj.get("currency")
        if currency:
            row.currency = currency.upper()
        row.external_subscription_id = obj.get("subscription") or row.external_subscription_id
        # 经 webhook metadata 现建的订单尚未 flush，provider_payload 仍是 None，先兜底成 {}。
        row.provider_payload = {**(row.provider_payload or {}), "checkout": obj}
        await self._mark_order_paid(
            session,
            row,
            transaction_id=obj.get("payment_intent"),
            provider_payload=row.provider_payload,
            period_start=_now(),
            period_end=_add_interval(_now(), row.interval),
        )

    async def _handle_stripe_subscription_update(self, session: AsyncSession, obj: dict[str, Any], settings: Settings) -> None:
        subscription_id = obj.get("id")
        if not subscription_id:
            return
        metadata = obj.get("metadata") or {}
        price = ((obj.get("items") or {}).get("data") or [{}])[0].get("price") or {}
        price_id = price.get("id")
        mapped = self._plan_interval_for_stripe_price(settings, price_id)
        plan = normalize_plan(metadata.get("plan") or (mapped[0] if mapped else None))
        interval = metadata.get("interval") or (mapped[1] if mapped else "monthly")
        user_id = metadata.get("user_id")
        if plan not in VALID_PAID_PLANS or interval not in VALID_INTERVALS or not user_id:
            logger.warning("Ignoring Stripe subscription without usable metadata: %s", subscription_id)
            return
        current_start = datetime.fromtimestamp(obj["current_period_start"], timezone.utc) if obj.get("current_period_start") else None
        current_end = datetime.fromtimestamp(obj["current_period_end"], timezone.utc) if obj.get("current_period_end") else None
        row = await session.scalar(
            select(BillingSubscription).where(
                BillingSubscription.provider == "stripe",
                BillingSubscription.external_subscription_id == subscription_id,
            )
        )
        if row is None:
            row = BillingSubscription(
                id=f"sub_{uuid.uuid4().hex}",
                user_id=user_id,
                provider="stripe",
                plan=plan,
                interval=interval,
                status=obj.get("status") or "unknown",
                external_subscription_id=subscription_id,
            )
            session.add(row)
        row.user_id = user_id
        row.plan = plan
        row.interval = interval
        row.status = obj.get("status") or row.status
        row.external_customer_id = obj.get("customer")
        row.external_price_id = price_id
        row.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
        row.current_period_start = current_start
        row.current_period_end = current_end
        row.provider_payload = obj
        if row.status in ACTIVE_SUBSCRIPTION_STATUSES and current_end is not None:
            await self._activate_membership(session, user_id, plan, "stripe", current_end)
        elif current_end is not None and current_end <= _now():
            await self.sync_expired_membership(session, user_id)

    async def _handle_stripe_subscription_deleted(self, session: AsyncSession, obj: dict[str, Any]) -> None:
        subscription_id = obj.get("id")
        if not subscription_id:
            return
        row = await session.scalar(
            select(BillingSubscription).where(
                BillingSubscription.provider == "stripe",
                BillingSubscription.external_subscription_id == subscription_id,
            )
        )
        if row is None:
            return
        row.status = obj.get("status") or "canceled"
        row.provider_payload = obj
        if row.current_period_end is None or row.current_period_end <= _now():
            await self.sync_expired_membership(session, row.user_id)


billing_service = BillingService()
