from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_equipment_item_crud_upsert_and_ownership() -> None:
    client = TestClient(create_app())
    owner = {"Authorization": "Bearer dev:eq-owner:eq-owner@example.com"}
    other = {"Authorization": "Bearer dev:eq-other:eq-other@example.com"}
    assert client.get("/v1/me", headers=owner).status_code == 200
    assert client.get("/v1/me", headers=other).status_code == 200

    created = client.post(
        "/v1/equipment",
        headers=owner,
        json={"category": "brewer", "name": " V60 01 ", "notes": "日常手冲"},
    )
    assert created.status_code == 200, created.text
    item = created.json()
    eq_id = item["id"]
    assert item["category"] == "brewer"
    assert item["name"] == "V60 01"
    assert item["notes"] == "日常手冲"
    assert item["is_default"] is True

    again = client.post(
        "/v1/equipment",
        headers=owner,
        json={"category": "brewer", "name": "v60 01", "notes": "更新备注"},
    )
    assert again.status_code == 200, again.text
    assert again.json()["id"] == eq_id
    assert again.json()["notes"] == "更新备注"
    assert len(client.get("/v1/equipment", headers=owner).json()) == 1

    assert client.get("/v1/equipment", headers=other).json() == []
    assert client.patch(f"/v1/equipment/{eq_id}", headers=other, json={"notes": "x"}).status_code == 404
    assert client.delete(f"/v1/equipment/{eq_id}", headers=other).status_code == 404

    patched = client.patch(
        f"/v1/equipment/{eq_id}",
        headers=owner,
        json={"name": "Hario V60 01", "notes": "周末用"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Hario V60 01"
    assert patched.json()["notes"] == "周末用"
    assert client.patch(f"/v1/equipment/{eq_id}", headers=owner, json={}).status_code == 400

    deleted = client.delete(f"/v1/equipment/{eq_id}", headers=owner)
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert client.get("/v1/equipment", headers=owner).json() == []


def test_equipment_defaults_are_per_category() -> None:
    client = TestClient(create_app())
    owner = {"Authorization": "Bearer dev:eq-def:eq-def@example.com"}
    assert client.get("/v1/me", headers=owner).status_code == 200

    brewer_a = client.post("/v1/equipment", headers=owner, json={"category": "brewer", "name": "V60"}).json()
    grinder = client.post("/v1/equipment", headers=owner, json={"category": "grinder", "name": "ZP6S"}).json()
    filter_media = client.post("/v1/equipment", headers=owner, json={"category": "filter_media", "name": "纸滤"}).json()
    assert brewer_a["is_default"] is True
    assert grinder["is_default"] is True
    assert filter_media["is_default"] is True

    brewer_b = client.post("/v1/equipment", headers=owner, json={"category": "brewer", "name": "Origami"}).json()
    assert brewer_b["is_default"] is False

    patched = client.patch(f"/v1/equipment/{brewer_b['id']}", headers=owner, json={"is_default": True})
    assert patched.status_code == 200, patched.text
    by_id = {item["id"]: item for item in client.get("/v1/equipment", headers=owner).json()}
    assert by_id[brewer_a["id"]]["is_default"] is False
    assert by_id[brewer_b["id"]]["is_default"] is True
    assert by_id[grinder["id"]]["is_default"] is True
    assert by_id[filter_media["id"]]["is_default"] is True

    cleared = client.patch(f"/v1/equipment/{brewer_b['id']}", headers=owner, json={"is_default": False})
    assert cleared.status_code == 200
    by_id = {item["id"]: item for item in client.get("/v1/equipment", headers=owner).json()}
    assert by_id[brewer_b["id"]]["is_default"] is False
    assert by_id[grinder["id"]]["is_default"] is True
