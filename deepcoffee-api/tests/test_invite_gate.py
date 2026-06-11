from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer dev:gate-admin:gate-admin@example.com"}


def test_invite_gate_blocks_until_redeemed() -> None:
    settings = get_settings()
    original = settings.enforce_invite_gate
    settings.enforce_invite_gate = True
    try:
        client = TestClient(create_app())
        user_headers = {"Authorization": "Bearer dev:gated-user:gated@example.com"}

        # 未绑定邀请码：业务接口 403 invite_required；/me 不受门禁影响（前端要靠它拿状态）。
        blocked = client.get("/v1/brew/records", headers=user_headers)
        assert blocked.status_code == 403
        assert blocked.json()["error"]["code"] == "invite_required"
        assert client.get("/v1/me", headers=user_headers).status_code == 200

        # 管理员发码 → 用户 redeem → 业务接口放行。
        # （本地无名单时任何登录用户可过 require_admin，与门禁互不影响。）
        created = client.post("/v1/admin/invites", headers=_admin_headers(), json={"count": 1})
        code = created.json()[0]["code"]
        assert client.post("/v1/invites/redeem", headers=user_headers, json={"code": code}).status_code == 200
        assert client.get("/v1/brew/records", headers=user_headers).status_code == 200
    finally:
        settings.enforce_invite_gate = original


def test_invite_gate_exempts_db_admin() -> None:
    settings = get_settings()
    original = settings.enforce_invite_gate
    settings.enforce_invite_gate = True
    try:
        client = TestClient(create_app())
        boot_headers = {"Authorization": "Bearer dev:gate-boot:gate-boot@example.com"}
        # 建档后直接把 role 提为 admin（模拟 bootstrap 注册者）。
        assert client.get("/v1/me", headers=boot_headers).status_code == 200
        promote = client.patch(
            "/v1/admin/users/gate-boot", headers=_admin_headers(), json={"role": "admin"}
        )
        assert promote.status_code == 200
        assert client.get("/v1/brew/records", headers=boot_headers).status_code == 200
    finally:
        settings.enforce_invite_gate = original


def test_disabled_account_blocked_everywhere() -> None:
    client = TestClient(create_app())
    victim_headers = {"Authorization": "Bearer dev:victim:victim@example.com"}
    assert client.get("/v1/me", headers=victim_headers).status_code == 200

    disabled = client.patch(
        "/v1/admin/users/victim", headers=_admin_headers(), json={"status": "disabled"}
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"

    # /me 与业务接口（门禁开关无关）都拒绝。
    me = client.get("/v1/me", headers=victim_headers)
    assert me.status_code == 403
    assert me.json()["error"]["code"] == "account_disabled"
    brew = client.get("/v1/brew/records", headers=victim_headers)
    assert brew.status_code == 403
    assert brew.json()["error"]["code"] == "account_disabled"

    # 恢复后放行。
    restored = client.patch(
        "/v1/admin/users/victim", headers=_admin_headers(), json={"status": "active"}
    )
    assert restored.status_code == 200
    assert client.get("/v1/me", headers=victim_headers).status_code == 200


def test_admin_cannot_demote_or_disable_self() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:self-admin:self@example.com"}
    assert client.get("/v1/me", headers=headers).status_code == 200

    for body in ({"role": "user"}, {"status": "disabled"}):
        resp = client.patch("/v1/admin/users/self-admin", headers=headers, json=body)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "cannot_modify_self"


def test_invite_revoke_lifecycle() -> None:
    client = TestClient(create_app())
    headers = _admin_headers()

    code = client.post("/v1/admin/invites", headers=headers, json={"count": 1}).json()[0]["code"]
    revoked = client.post(f"/v1/admin/invites/{code}/revoke", headers=headers)
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    # 作废后不可用、重复作废幂等、不存在的码 404。
    assert client.post("/v1/invites/validate", json={"code": code}).json()["valid"] is False
    assert client.post(f"/v1/admin/invites/{code}/revoke", headers=headers).status_code == 200
    assert client.post("/v1/admin/invites/DC-NOPE-NOPE/revoke", headers=headers).status_code == 404

    # 已使用的码不可作废（409）。
    used_code = client.post("/v1/admin/invites", headers=headers, json={"count": 1}).json()[0]["code"]
    user_headers = {"Authorization": "Bearer dev:revoke-user:revoke@example.com"}
    assert client.post("/v1/invites/redeem", headers=user_headers, json={"code": used_code}).status_code == 200
    conflict = client.post(f"/v1/admin/invites/{used_code}/revoke", headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "invite_already_used"


def test_admin_stats_counts() -> None:
    client = TestClient(create_app())
    headers = _admin_headers()

    client.post("/v1/admin/invites", headers=headers, json={"count": 2})
    client.get("/v1/me", headers={"Authorization": "Bearer dev:stats-user:stats@example.com"})

    stats = client.get("/v1/admin/stats", headers=headers)
    assert stats.status_code == 200
    body = stats.json()
    assert body["user_count"] >= 1
    assert body["active_invite_count"] >= 2
    for key in ("pending_proposal_count", "pending_candidate_count", "active_entity_count"):
        assert body[key] >= 0
