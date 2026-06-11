from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_and_dependencies() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    dependencies = client.get("/v1/health/dependencies")
    assert dependencies.status_code == 200
    assert dependencies.json()["knowledge"]["status"] == "ok"


def test_invite_and_profile_flow() -> None:
    client = TestClient(create_app())

    # 默认不再预置「万能码」：未经管理员生成的码（含旧 DEEP-BETA）一律无效。
    invite = client.post("/v1/invites/validate", json={"code": "DEEP-BETA"})
    assert invite.status_code == 200
    assert invite.json()["valid"] is False

    headers = {"Authorization": "Bearer dev:user-1:user@example.com"}
    profile = client.get("/v1/me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["id"] == "user-1"
    assert profile.json()["email"] == "user@example.com"

    updated = client.patch(
        "/v1/me",
        headers=headers,
        json={"display_name": "Deep Coffee Tester", "timezone": "Asia/Shanghai", "unit_system": "metric"},
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Deep Coffee Tester"

    quota = client.get("/v1/me/quota", headers=headers)
    assert quota.status_code == 200
    assert quota.json()["ai_total"] == 500
    assert quota.json()["ai_used"] == 0
    assert "records_used" not in quota.json()


def test_admin_create_and_redeem_invite() -> None:
    client = TestClient(create_app())
    admin_headers = {"Authorization": "Bearer dev:admin-1:admin@example.com"}
    user_headers = {"Authorization": "Bearer dev:user-9:user9@example.com"}

    # Admin creates two invite codes.
    created = client.post("/v1/admin/invites", headers=admin_headers, json={"count": 2, "note": "beta"})
    assert created.status_code == 200
    codes = [item["code"] for item in created.json()]
    assert len(codes) == 2

    listed = client.get("/v1/admin/invites", headers=admin_headers)
    assert listed.status_code == 200
    assert {item["code"] for item in listed.json()} >= set(codes)

    # User redeems one code: first time succeeds, second time fails (already used).
    redeem = client.post("/v1/invites/redeem", headers=user_headers, json={"code": codes[0]})
    assert redeem.status_code == 200
    assert redeem.json()["redeemed"] is True

    again = client.post("/v1/invites/redeem", headers=user_headers, json={"code": codes[0]})
    assert again.status_code == 400

    # 消费后，管理员列表应把该码标记 used，并把消费者 uid 解析成可读邮箱。
    relisted = client.get("/v1/admin/invites", headers=admin_headers)
    used_item = next(item for item in relisted.json() if item["code"] == codes[0])
    assert used_item["status"] == "used"
    assert used_item["used_by"] == "user-9"
    assert used_item["used_by_email"] == "user9@example.com"

    # 万能码已停用：DEEP-BETA 与未知码都应被拒。
    assert client.post("/v1/invites/redeem", headers=user_headers, json={"code": "DEEP-BETA"}).status_code == 400
    assert client.post("/v1/invites/redeem", headers=user_headers, json={"code": "NOPE-NOPE"}).status_code == 400
