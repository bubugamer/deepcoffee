from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.main import create_app
from app.models.tables import UserProfile
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

        # 前两次放行，第三次门禁拦截 402。
        assert _ask(client, headers).status_code == 200
        assert _ask(client, headers).status_code == 200
        blocked = _ask(client, headers)
        assert blocked.status_code == 402
        assert blocked.json()["error"]["code"] == "ai_quota_exceeded"
    finally:
        settings.ai_quota_basic = original


def test_pro_plan_is_unlimited() -> None:
    settings = get_settings()
    original = settings.ai_quota_basic
    settings.ai_quota_basic = 2
    try:
        client = TestClient(create_app())
        headers = {"Authorization": "Bearer dev:pro-user:pro@example.com"}

        # 建档后升为 pro。
        assert client.get("/v1/me", headers=headers).status_code == 200
        _set_plan("pro-user", "pro")

        # pro：ai_total 为 None（无限），且连调超过 basic 阈值仍放行。
        quota = client.get("/v1/me/quota", headers=headers)
        assert quota.status_code == 200
        assert quota.json()["ai_total"] is None
        assert quota.json()["plan"] == "pro"

        for _ in range(3):
            assert _ask(client, headers).status_code == 200
    finally:
        settings.ai_quota_basic = original


def test_billing_plans_reflect_launch_pricing() -> None:
    client = TestClient(create_app())
    resp = client.get("/v1/billing/plans")
    assert resp.status_code == 200
    plans = {p["id"]: p for p in resp.json()}

    basic = plans["basic"]
    assert basic["price"] == 0
    assert basic["request_limit"] == get_settings().ai_quota_basic  # 默认 500
    assert any("次 / 月" in f for f in basic["features"])

    pro = plans["pro"]
    assert pro["price"] == 49
    assert pro["request_limit"] is None  # 无限


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
