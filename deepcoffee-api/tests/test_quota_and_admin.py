from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.main import create_app
from app.models.tables import UserProfile
from app.repositories.usage import current_month_window
from app.services.bootstrap import seed_bootstrap_invite_code


def _set_plan(user_id: str, plan: str) -> None:
    async def _run() -> None:
        async with get_sessionmaker()() as session:
            await session.execute(update(UserProfile).where(UserProfile.id == user_id).values(plan=plan))
            await session.commit()

    asyncio.run(_run())


def _ask(client: TestClient, headers: dict[str, str]):
    return client.post("/v1/knowledge/ask", headers=headers, json={"question": "手冲咖啡粉水比一般是多少？"})


def test_basic_quota_gate_blocks_after_limit() -> None:
    settings = get_settings()
    original = settings.ai_quota_basic
    settings.ai_quota_basic = 2
    try:
        client = TestClient(create_app())
        headers = {"Authorization": "Bearer dev:gate-user:gate@example.com"}

        # 展示数应随配置变为 2。
        quota = client.get("/v1/me/quota", headers=headers)
        assert quota.status_code == 200
        assert quota.json()["ai_total"] == 2
        assert quota.json()["ai_remaining"] == 2

        # 前两次放行，第三次门禁拦截 402。
        assert _ask(client, headers).status_code == 200
        assert _ask(client, headers).status_code == 200
        blocked = _ask(client, headers)
        assert blocked.status_code == 402
        assert blocked.json()["error"]["code"] == "ai_quota_exceeded"
    finally:
        settings.ai_quota_basic = original


def test_pro_plan_uses_its_own_monthly_quota() -> None:
    settings = get_settings()
    original_basic = settings.ai_quota_basic
    original_pro = settings.ai_quota_pro
    settings.ai_quota_basic = 2
    settings.ai_quota_pro = 3
    try:
        client = TestClient(create_app())
        headers = {"Authorization": "Bearer dev:pro-user:pro@example.com"}

        # 建档后升为 pro。
        assert client.get("/v1/me", headers=headers).status_code == 200
        _set_plan("pro-user", "pro")

        # pro：使用自己的有限额度，不再是无限。
        quota = client.get("/v1/me/quota", headers=headers)
        assert quota.status_code == 200
        assert quota.json()["ai_total"] == 3
        assert quota.json()["ai_remaining"] == 3
        assert quota.json()["plan"] == "pro"

        for _ in range(3):
            assert _ask(client, headers).status_code == 200
        blocked = _ask(client, headers)
        assert blocked.status_code == 402
        assert blocked.json()["error"]["code"] == "ai_quota_exceeded"
    finally:
        settings.ai_quota_basic = original_basic
        settings.ai_quota_pro = original_pro


def test_billing_plans_reflect_launch_pricing() -> None:
    client = TestClient(create_app())
    resp = client.get("/v1/billing/plans")
    assert resp.status_code == 200
    plans = {p["id"]: p for p in resp.json()}

    basic = plans["basic"]
    assert basic["price"] == 0
    assert basic["request_limit"] == get_settings().ai_quota_basic
    assert any("次 / 月" in f for f in basic["features"])

    pro = plans["pro"]
    assert pro["price"] == 59
    assert pro["request_limit"] == get_settings().ai_quota_pro

    max_plan = plans["max"]
    assert max_plan["price"] == 99
    assert max_plan["request_limit"] == get_settings().ai_quota_max


def test_bootstrap_invite_grants_admin_role() -> None:
    """初始化闭环：bootstrap 码入库 → 注册者得 admin role → 守卫拦住后续部署的新码。"""
    settings = get_settings()
    original_bootstrap = settings.bootstrap_invite_code
    original_admins = settings.admin_user_ids
    # 配一个无关的环境变量管理员，关闭「本地未配名单则人人是管理员」的便利通道，
    # 逼着 require_admin 走 DB role 分支。
    settings.admin_user_ids = ["env-admin-elsewhere"]
    settings.bootstrap_invite_code = "DC-BOOT-T3ST"
    try:
        client = TestClient(create_app())
        boot_headers = {"Authorization": "Bearer dev:boot-user:boot@example.com"}
        other_headers = {"Authorization": "Bearer dev:plain-user:plain@example.com"}

        # TestClient 不跑 lifespan，手动执行启动期的 seed。
        asyncio.run(seed_bootstrap_invite_code(settings))

        # 用 bootstrap 码注册 → role 自动变为 admin。
        redeem = client.post("/v1/invites/redeem", headers=boot_headers, json={"code": "DC-BOOT-T3ST"})
        assert redeem.status_code == 200
        me = client.get("/v1/me", headers=boot_headers)
        assert me.status_code == 200
        assert me.json()["role"] == "admin"

        # DB role 管理员可调管理接口；普通用户被拒。
        assert client.get("/v1/admin/invites", headers=boot_headers).status_code == 200
        denied = client.get("/v1/admin/invites", headers=other_headers)
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "admin_required"

        # 守卫：已有 admin 后，重新部署生成的新码不再入库。
        settings.bootstrap_invite_code = "DC-BOOT-AGA1N"
        asyncio.run(seed_bootstrap_invite_code(settings))
        validate = client.post("/v1/invites/validate", json={"code": "DC-BOOT-AGA1N"})
        assert validate.status_code == 200
        assert validate.json()["valid"] is False
    finally:
        settings.bootstrap_invite_code = original_bootstrap
        settings.admin_user_ids = original_admins


def test_admin_users_lists_invite_binding() -> None:
    client = TestClient(create_app())
    admin_headers = {"Authorization": "Bearer dev:admin-1:admin@example.com"}
    user_headers = {"Authorization": "Bearer dev:user-42:user42@example.com"}

    created = client.post("/v1/admin/invites", headers=admin_headers, json={"count": 1, "note": "beta"})
    assert created.status_code == 200
    code = created.json()[0]["code"]

    redeem = client.post("/v1/invites/redeem", headers=user_headers, json={"code": code})
    assert redeem.status_code == 200

    users = client.get("/v1/admin/users", headers=admin_headers)
    assert users.status_code == 200
    row = next(item for item in users.json() if item["id"] == "user-42")
    assert row["email"] == "user42@example.com"
    assert row["plan"] == "basic"
    assert row["invite_code"] == code
    assert row["invited_at"] is not None
    assert row["ai_used"] == 0
    assert row["ai_total"] == get_settings().ai_quota_basic
    assert row["ai_remaining"] == get_settings().ai_quota_basic
    assert row["quota_custom"] is False


def test_admin_can_set_custom_monthly_limit_and_gate_updates_immediately() -> None:
    client = TestClient(create_app())
    admin_headers = {"Authorization": "Bearer dev:admin-1:admin@example.com"}
    user_headers = {"Authorization": "Bearer dev:quota-user:quota@example.com"}

    assert client.get("/v1/me", headers=user_headers).status_code == 200
    updated = client.patch(
        "/v1/admin/users/quota-user/quota",
        headers=admin_headers,
        json={"monthly_limit": 1, "reason": "internal beta limit"},
    )
    assert updated.status_code == 200
    assert updated.json()["ai_total"] == 1
    assert updated.json()["ai_remaining"] == 1
    assert updated.json()["quota_custom"] is True

    quota = client.get("/v1/me/quota", headers=user_headers)
    assert quota.status_code == 200
    body = quota.json()
    assert body["ai_total"] == 1
    assert body["ai_remaining"] == 1
    assert datetime.fromisoformat(body["reset_at"]) == current_month_window()[1]

    assert _ask(client, user_headers).status_code == 200
    blocked = _ask(client, user_headers)
    assert blocked.status_code == 402
    assert blocked.json()["error"]["code"] == "ai_quota_exceeded"


def test_admin_can_adjust_used_this_month_without_deleting_usage_events() -> None:
    client = TestClient(create_app())
    admin_headers = {"Authorization": "Bearer dev:admin-1:admin@example.com"}
    user_headers = {"Authorization": "Bearer dev:adjust-user:adjust@example.com"}

    assert client.get("/v1/me", headers=user_headers).status_code == 200
    assert _ask(client, user_headers).status_code == 200

    adjusted = client.patch(
        "/v1/admin/users/adjust-user/quota",
        headers=admin_headers,
        json={"monthly_limit": 3, "used_this_month": 2, "reason": "manual correction"},
    )
    assert adjusted.status_code == 200
    assert adjusted.json()["ai_used"] == 2
    assert adjusted.json()["ai_total"] == 3
    assert adjusted.json()["ai_remaining"] == 1

    usage = client.get("/v1/billing/usage", headers=user_headers)
    assert usage.status_code == 200
    assert usage.json()["total_requests"] == 2

    assert _ask(client, user_headers).status_code == 200
    blocked = _ask(client, user_headers)
    assert blocked.status_code == 402

    reset = client.patch(
        "/v1/admin/users/adjust-user/quota",
        headers=admin_headers,
        json={"monthly_limit": None, "used_this_month": 0, "reason": "reset to plan default"},
    )
    assert reset.status_code == 200
    assert reset.json()["ai_total"] == get_settings().ai_quota_basic
    assert reset.json()["ai_used"] == 0
    assert reset.json()["quota_custom"] is False


# ── 管理操作审计（admin_audit_events + GET /admin/users/{id}/audit）──

def test_admin_changes_are_audited_and_listed() -> None:
    client = TestClient(create_app())
    admin_headers = {"Authorization": "Bearer dev:admin-1:admin@example.com"}
    user_headers = {"Authorization": "Bearer dev:audit-user:audit@example.com"}
    user_id = client.get("/v1/me", headers=user_headers).json()["id"]

    # 改角色 + 套餐（两个字段 → 两条审计）
    resp = client.patch(
        f"/v1/admin/users/{user_id}", headers=admin_headers,
        json={"role": "admin", "plan": "max"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["plan"] == "max"
    # 调额度：上限 + 已用 + 原因
    resp = client.patch(
        f"/v1/admin/users/{user_id}/quota", headers=admin_headers,
        json={"monthly_limit": 1000, "used_this_month": 3, "reason": "beta 补偿"},
    )
    assert resp.status_code == 200, resp.text

    events = client.get(f"/v1/admin/users/{user_id}/audit", headers=admin_headers).json()
    actions = [e["action"] for e in events]
    # 倒序：最新（额度）在前
    assert set(actions) == {"role_change", "plan_change", "quota_limit_change", "usage_adjust"}
    role_evt = next(e for e in events if e["action"] == "role_change")
    assert role_evt["before_value"] == "user" and role_evt["after_value"] == "admin"
    assert role_evt["actor_email"] == "admin@example.com"
    limit_evt = next(e for e in events if e["action"] == "quota_limit_change")
    assert limit_evt["before_value"] == "套餐默认" and limit_evt["after_value"] == "1000"
    assert limit_evt["reason"] == "beta 补偿"
    used_evt = next(e for e in events if e["action"] == "usage_adjust")
    assert used_evt["before_value"] == "0" and used_evt["after_value"] == "3"


def test_noop_admin_changes_are_not_audited() -> None:
    client = TestClient(create_app())
    admin_headers = {"Authorization": "Bearer dev:admin-1:admin@example.com"}
    user_headers = {"Authorization": "Bearer dev:audit-noop:audit-noop@example.com"}
    user_id = client.get("/v1/me", headers=user_headers).json()["id"]

    # 传与现状相同的值：plan 默认 basic、used 当前 0 → 不落审计
    assert client.patch(
        f"/v1/admin/users/{user_id}", headers=admin_headers, json={"plan": "basic"}
    ).status_code == 200
    assert client.patch(
        f"/v1/admin/users/{user_id}/quota", headers=admin_headers, json={"used_this_month": 0}
    ).status_code == 200

    events = client.get(f"/v1/admin/users/{user_id}/audit", headers=admin_headers).json()
    assert events == []


def test_audit_endpoint_requires_admin_and_existing_user() -> None:
    settings = get_settings()
    original_admins = settings.admin_user_ids
    # 关闭「本地未配名单则人人是管理员」便利通道，逼出 403 分支。
    settings.admin_user_ids = ["admin-1"]
    try:
        client = TestClient(create_app())
        admin_headers = {"Authorization": "Bearer dev:admin-1:admin@example.com"}
        user_headers = {"Authorization": "Bearer dev:audit-plain:audit-plain@example.com"}
        user_id = client.get("/v1/me", headers=user_headers).json()["id"]

        denied = client.get(f"/v1/admin/users/{user_id}/audit", headers=user_headers)
        assert denied.status_code == 403
        missing = client.get("/v1/admin/users/no-such-user/audit", headers=admin_headers)
        assert missing.status_code == 404
    finally:
        settings.admin_user_ids = original_admins
