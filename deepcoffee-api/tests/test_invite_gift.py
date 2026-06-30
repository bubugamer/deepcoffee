from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.main import create_app
from app.models.tables import UserProfile
from app.services.billing_service import _add_months


def _admin_headers(uid: str = "gift-admin") -> dict[str, str]:
    return {"Authorization": f"Bearer dev:{uid}:{uid}@example.com"}


def _user_headers(uid: str) -> dict[str, str]:
    return {"Authorization": f"Bearer dev:{uid}:{uid}@example.com"}


def test_add_months_clamps_and_wraps() -> None:
    assert _add_months(datetime(2026, 1, 31, tzinfo=timezone.utc), 1).date().isoformat() == "2026-02-28"
    assert _add_months(datetime(2026, 1, 31, tzinfo=timezone.utc), 12).date().isoformat() == "2027-01-31"
    assert _add_months(datetime(2026, 11, 15, tzinfo=timezone.utc), 3).date().isoformat() == "2027-02-15"
    assert _add_months(datetime(2026, 6, 30, tzinfo=timezone.utc), 6).date().isoformat() == "2026-12-30"


def test_admin_creates_gift_code_and_validate_reports_gift() -> None:
    client = TestClient(create_app())
    created = client.post(
        "/v1/admin/invites",
        headers=_admin_headers(),
        json={"count": 1, "gift_plan": "pro", "gift_duration_months": 6},
    )
    assert created.status_code == 200
    row = created.json()[0]
    assert row["gift_plan"] == "pro"
    assert row["gift_duration_months"] == 6

    res = client.post("/v1/invites/validate", json={"code": row["code"]}).json()
    assert res["valid"] is True
    assert res["gift_plan"] == "pro"
    assert res["gift_duration_months"] == 6


def test_redeem_gift_code_opens_membership_with_expiry() -> None:
    client = TestClient(create_app())
    code = client.post(
        "/v1/admin/invites",
        headers=_admin_headers("gift-admin-2"),
        json={"count": 1, "gift_plan": "max", "gift_duration_months": 3},
    ).json()[0]["code"]

    user = _user_headers("gift-user")
    assert client.get("/v1/me", headers=user).status_code == 200  # 先建档
    assert client.post("/v1/invites/redeem", headers=user, json={"code": code}).status_code == 200

    me = client.get("/v1/me", headers=user).json()
    assert me["plan"] == "max"
    assert me["plan_source"] == "invite"
    assert me["plan_expires_at"] is not None
    got = datetime.fromisoformat(me["plan_expires_at"])
    expected = _add_months(datetime.now(timezone.utc), 3)
    assert abs((got - expected).total_seconds()) < 86400


def test_open_registration_allows_access_without_invite() -> None:
    # 公测放开：门禁关闭时，未填邀请码的用户也能访问业务接口。
    settings = get_settings()
    original = settings.enforce_invite_gate
    settings.enforce_invite_gate = False
    try:
        client = TestClient(create_app())
        assert client.get("/v1/brew/records", headers=_user_headers("open-user")).status_code == 200
    finally:
        settings.enforce_invite_gate = original


def test_invite_gift_membership_downgrades_on_expiry() -> None:
    client = TestClient(create_app())

    async def seed() -> None:
        async with get_sessionmaker()() as session:
            session.add(
                UserProfile(
                    id="invite-expired",
                    email="invite-expired@example.com",
                    plan="pro",
                    plan_source="invite",
                    plan_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
            )
            await session.commit()

    asyncio.run(seed())
    me = client.get("/v1/me", headers=_user_headers("invite-expired")).json()
    assert me["plan"] == "basic"
    assert me["plan_source"] == "expired"
