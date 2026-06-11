from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_equipment_crud_and_ownership() -> None:
    client = TestClient(create_app())
    owner = {"Authorization": "Bearer dev:eq-owner:eq-owner@example.com"}
    other = {"Authorization": "Bearer dev:eq-other:eq-other@example.com"}
    # 建档（require_member 在测试默认关门禁，但 profile 仍按需建）
    assert client.get("/v1/me", headers=owner).status_code == 200
    assert client.get("/v1/me", headers=other).status_code == 200

    # 创建
    created = client.post("/v1/equipment", headers=owner, json={
        "brew_method": "V60", "grinder": "C40", "filter_media": "纸滤", "water": "农夫山泉", "label": "日常手冲",
    })
    assert created.status_code == 200
    eq_id = created.json()["id"]

    # 同 (brew_method, grinder, filter_media) 再建 → upsert 合并，不重复
    again = client.post("/v1/equipment", headers=owner, json={
        "brew_method": "V60", "grinder": "C40", "filter_media": "纸滤", "water": "Vivid",
    })
    assert again.json()["id"] == eq_id
    assert again.json()["water"] == "Vivid"

    # 列表
    listed = client.get("/v1/equipment", headers=owner)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # 他人不可见 / 不可改 / 不可删
    assert client.get("/v1/equipment", headers=other).json() == []
    assert client.patch(f"/v1/equipment/{eq_id}", headers=other, json={"label": "x"}).status_code == 404
    assert client.delete(f"/v1/equipment/{eq_id}", headers=other).status_code == 404

    # 更新
    patched = client.patch(f"/v1/equipment/{eq_id}", headers=owner, json={"label": "周末出品", "water": "三顿半"})
    assert patched.status_code == 200
    assert patched.json()["label"] == "周末出品"
    # 空更新 400
    assert client.patch(f"/v1/equipment/{eq_id}", headers=owner, json={}).status_code == 400

    # 删除
    assert client.delete(f"/v1/equipment/{eq_id}", headers=owner).json() == {"deleted": True}
    assert client.get("/v1/equipment", headers=owner).json() == []


def test_equipment_default_invariant() -> None:
    client = TestClient(create_app())
    owner = {"Authorization": "Bearer dev:eq-def:eq-def@example.com"}
    assert client.get("/v1/me", headers=owner).status_code == 200

    # 第一套自动设为默认
    a = client.post("/v1/equipment", headers=owner, json={
        "brew_method": "V60", "grinder": "ZP6S", "filter_media": "纸滤",
    }).json()
    assert a["is_default"] is True

    # 第二套不抢默认
    b = client.post("/v1/equipment", headers=owner, json={
        "brew_method": "爱乐压", "grinder": "C40", "filter_media": "金属滤网",
    }).json()
    assert b["is_default"] is False

    # PATCH 设 B 为默认 → A 自动取消（单默认不变量）；只传 is_default 不算空更新
    patched = client.patch(f"/v1/equipment/{b['id']}", headers=owner, json={"is_default": True})
    assert patched.status_code == 200
    assert patched.json()["is_default"] is True
    by_id = {item["id"]: item for item in client.get("/v1/equipment", headers=owner).json()}
    assert by_id[a["id"]]["is_default"] is False
    assert by_id[b["id"]]["is_default"] is True

    # is_default=False 允许回到「无默认」状态
    assert client.patch(f"/v1/equipment/{b['id']}", headers=owner, json={"is_default": False}).json()["is_default"] is False
    assert all(not item["is_default"] for item in client.get("/v1/equipment", headers=owner).json())
