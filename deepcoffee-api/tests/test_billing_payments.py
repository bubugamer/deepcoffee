from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.main import create_app
from app.models.tables import BillingPaymentOrder, UserProfile
from app.services.billing_service import billing_service


def _headers(user_id: str = "pay-user", email: str = "pay@example.com") -> dict[str, str]:
    return {"Authorization": f"Bearer dev:{user_id}:{email}"}


def _configure_alipay() -> None:
    settings = get_settings()
    settings.alipay_app_id = "app_123"
    settings.alipay_app_private_key = "fake-private"
    settings.alipay_public_key = "fake-public"
    settings.alipay_seller_id = "seller_123"
    settings.backend_public_url = "https://api.example.com"


def _configure_stripe() -> None:
    settings = get_settings()
    settings.frontend_public_url = "https://deepcoffee.app"
    settings.stripe_secret_key = "sk_test_123"
    settings.stripe_webhook_secret = "whsec_test"
    settings.stripe_price_pro_monthly = "price_pro_m"
    settings.stripe_price_pro_yearly = "price_pro_y"
    settings.stripe_price_max_monthly = "price_max_m"
    settings.stripe_price_max_yearly = "price_max_y"


def _stripe_signature(payload: bytes) -> str:
    secret = get_settings().stripe_webhook_secret or ""
    timestamp = str(int(time.time()))
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def test_billing_plans_include_monthly_and_yearly_prices() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/billing/plans")

    assert response.status_code == 200
    plans = {item["id"]: item for item in response.json()}
    assert plans["pro"]["prices"]["monthly"]["amount"] == 59
    assert plans["pro"]["prices"]["yearly"]["amount"] == 568
    assert plans["max"]["prices"]["monthly"]["amount"] == 99
    assert plans["max"]["prices"]["yearly"]["amount"] == 938


def test_alipay_order_notify_opens_membership(monkeypatch) -> None:
    _configure_alipay()
    client = TestClient(create_app())

    async def fake_precreate(*_args, **_kwargs):
        return {"code": "10000", "qr_code": "https://qr.alipay.test/order"}

    monkeypatch.setattr(billing_service, "_alipay_precreate", fake_precreate)
    monkeypatch.setattr(billing_service, "_verify_alipay_signature", lambda *_args, **_kwargs: True)

    created = client.post(
        "/v1/billing/alipay/orders",
        headers=_headers(),
        json={"plan": "pro", "interval": "yearly"},
    )
    assert created.status_code == 200
    order = created.json()
    assert order["amount"] == 568
    assert order["qr_code"] == "https://qr.alipay.test/order"

    notified = client.post(
        "/v1/billing/alipay/notify",
        data={
            "app_id": "app_123",
            "seller_id": "seller_123",
            "out_trade_no": order["id"],
            "trade_no": "ali_trade_1",
            "trade_status": "TRADE_SUCCESS",
            "total_amount": "568.00",
            "sign": "fake",
        },
    )
    assert notified.status_code == 200
    assert notified.text == "success"

    profile = client.get("/v1/me", headers=_headers())
    assert profile.status_code == 200
    body = profile.json()
    assert body["plan"] == "pro"
    assert body["plan_source"] == "alipay"
    assert body["plan_expires_at"] is not None

    status = client.get(f"/v1/billing/orders/{order['id']}", headers=_headers())
    assert status.status_code == 200
    assert status.json()["status"] == "paid"


def test_stripe_checkout_and_webhook_open_membership(monkeypatch) -> None:
    _configure_stripe()
    client = TestClient(create_app())

    async def fake_checkout(*_args, **_kwargs):
        return {"id": "cs_test_123", "url": "https://checkout.stripe.test/session"}

    monkeypatch.setattr(billing_service, "_stripe_create_checkout_session", fake_checkout)

    checkout = client.post(
        "/v1/billing/stripe/checkout",
        headers=_headers("stripe-user", "stripe@example.com"),
        json={"plan": "max", "interval": "monthly"},
    )
    assert checkout.status_code == 200
    assert checkout.json()["checkout_url"] == "https://checkout.stripe.test/session"
    order_id = checkout.json()["id"]

    event = {
        "id": "evt_checkout_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "client_reference_id": "stripe-user",
                "subscription": "sub_123",
                "metadata": {"user_id": "stripe-user", "plan": "max", "interval": "monthly"},
            }
        },
    }
    payload = json.dumps(event, separators=(",", ":")).encode()
    webhook = client.post(
        "/v1/billing/stripe/webhook",
        content=payload,
        headers={"stripe-signature": _stripe_signature(payload), "content-type": "application/json"},
    )
    assert webhook.status_code == 200

    profile = client.get("/v1/me", headers=_headers("stripe-user", "stripe@example.com"))
    assert profile.status_code == 200
    body = profile.json()
    assert body["plan"] == "max"
    assert body["plan_source"] == "stripe"

    order = client.get(f"/v1/billing/orders/{order_id}", headers=_headers("stripe-user", "stripe@example.com"))
    assert order.status_code == 200
    assert order.json()["status"] == "paid"


def test_stripe_webhook_creates_order_from_metadata_when_missing(monkeypatch) -> None:
    # webhook 先于/绕过我们的下单接口到达：库里没有对应订单时，应据 metadata 现建并开通会员，
    # 不能因为新建行的 provider_payload 尚未落库（None）而崩溃；金额 / 币种取自 webhook。
    _configure_stripe()
    client = TestClient(create_app())

    # _activate_membership 需要 user_profiles 行先存在。
    assert client.get("/v1/me", headers=_headers("stripe-oob", "oob@example.com")).status_code == 200

    event = {
        "id": "evt_oob_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_oob_no_order",
                "client_reference_id": "stripe-oob",
                "subscription": "sub_oob",
                "amount_total": 9900,
                "currency": "hkd",
                "metadata": {"user_id": "stripe-oob", "plan": "max", "interval": "monthly"},
            }
        },
    }
    payload = json.dumps(event, separators=(",", ":")).encode()
    webhook = client.post(
        "/v1/billing/stripe/webhook",
        content=payload,
        headers={"stripe-signature": _stripe_signature(payload), "content-type": "application/json"},
    )
    assert webhook.status_code == 200

    profile = client.get("/v1/me", headers=_headers("stripe-oob", "oob@example.com")).json()
    assert profile["plan"] == "max"
    assert profile["plan_source"] == "stripe"

    rows = client.get("/v1/admin/payments", headers=_headers("admin-pay", "admin@example.com")).json()
    created = next(row for row in rows if row["external_order_id"] == "cs_oob_no_order")
    assert created["status"] == "paid"
    assert created["amount"] == 99.0
    assert created["currency"] == "HKD"


def test_expired_paid_membership_downgrades_on_profile_read() -> None:
    client = TestClient(create_app())

    async def seed() -> None:
        async_session = get_sessionmaker()
        async with async_session() as session:
            session.add(
                UserProfile(
                    id="expired-user",
                    email="expired@example.com",
                    plan="pro",
                    plan_source="alipay",
                    plan_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
            )
            await session.commit()

    import asyncio

    asyncio.run(seed())

    profile = client.get("/v1/me", headers=_headers("expired-user", "expired@example.com"))

    assert profile.status_code == 200
    assert profile.json()["plan"] == "basic"
    assert profile.json()["plan_source"] == "expired"


def test_admin_can_list_payment_records(monkeypatch) -> None:
    _configure_alipay()
    client = TestClient(create_app())

    async def fake_precreate(*_args, **_kwargs):
        return {"code": "10000", "qr_code": "https://qr.alipay.test/order"}

    monkeypatch.setattr(billing_service, "_alipay_precreate", fake_precreate)

    created = client.post(
        "/v1/billing/alipay/orders",
        headers=_headers("pay-list-user", "list@example.com"),
        json={"plan": "max", "interval": "yearly"},
    )
    assert created.status_code == 200

    payments = client.get("/v1/admin/payments", headers=_headers("admin-pay", "admin@example.com"))

    assert payments.status_code == 200
    rows = payments.json()
    assert rows[0]["provider"] == "alipay"
    assert rows[0]["plan"] == "max"
    assert rows[0]["interval"] == "yearly"
    assert rows[0]["user_email"] == "list@example.com"


def test_alipay_query_can_mark_paid(monkeypatch) -> None:
    _configure_alipay()
    client = TestClient(create_app())

    async def fake_precreate(*_args, **_kwargs):
        return {"code": "10000", "qr_code": "https://qr.alipay.test/order"}

    async def fake_query(*_args, **_kwargs):
        return {"code": "10000", "trade_status": "TRADE_SUCCESS", "trade_no": "ali_query_1"}

    monkeypatch.setattr(billing_service, "_alipay_precreate", fake_precreate)
    monkeypatch.setattr(billing_service, "_alipay_query", fake_query)

    created = client.post(
        "/v1/billing/alipay/orders",
        headers=_headers("query-user", "query@example.com"),
        json={"plan": "pro", "interval": "monthly"},
    )
    order_id = created.json()["id"]

    queried = client.post(f"/v1/billing/alipay/orders/{order_id}/query", headers=_headers("query-user", "query@example.com"))

    assert queried.status_code == 200
    assert queried.json()["status"] == "paid"

    async def check() -> str:
        async_session = get_sessionmaker()
        async with async_session() as session:
            row = await session.get(BillingPaymentOrder, order_id)
            assert row is not None
            return row.external_transaction_id or ""

    import asyncio

    assert asyncio.run(check()) == "ali_query_1"
