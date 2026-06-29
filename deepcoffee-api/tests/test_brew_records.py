from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.db import get_sessionmaker
from app.main import create_app
from app.models.tables import UserProfile


def _set_plan(user_id: str, plan: str) -> None:
    async def _run() -> None:
        async with get_sessionmaker()() as session:
            await session.execute(update(UserProfile).where(UserProfile.id == user_id).values(plan=plan))
            await session.commit()

    asyncio.run(_run())


def _confirm_test_bean(client: TestClient, headers: dict[str, str], name: str = "表单新增测试豆") -> str:
    response = client.post(
        "/v1/beans/confirm",
        headers=headers,
        json={
            "draft": {
                "name": name,
                "roaster_name": "测试烘焙",
                "bean_components": [
                    {"origin_name": "巴拿马", "process_name": "水洗", "varietal_names": ["瑰夏"]}
                ],
            }
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["bean_id"]


def test_brew_record_lifecycle_and_unified_ai_quota() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:brew-user-1:brew@example.com"}
    bean_id = _confirm_test_bean(client, headers, name="千峰庄园 帕卡马拉 CM 日晒")

    parsed = client.post(
        "/v1/brew/parse",
        headers=headers,
        json={"input": "今天用 V60 和 C40 #19 冲了千峰庄园帕卡马拉，15g，225ml，93度，甜感不错"},
    )
    assert parsed.status_code == 200
    assert parsed.json()["draft"]["device"] == "V60"
    assert parsed.json()["draft"]["grind_setting"] == "#19"

    first = client.post(
        "/v1/brew/confirm",
        headers=headers,
        json={
            "bean_card_id": bean_id,
            "draft": {
                "bean_name": "千峰庄园 帕卡马拉 CM 日晒",
                "origin": "巴拿马",
                "device": "V60",
                "grinder": "C40 #19",
                "grind_setting": "#19",
                "dose_g": 15,
                "water_ml": 225,
                "water_temp_c": 93,
                "brew_time_seconds": 155,
                "evaluation": {
                    "overall": {"score": 4, "description": "整体甜感清楚"},
                    "aroma": {"score": 4, "description": "花香明显"},
                    "flavor": {"score": 4, "description": "水果感清晰"},
                    "aftertaste": {"score": 3, "description": "余韵中等"},
                    "acidity": {"score": 3, "description": "酸质明亮"},
                    "body": {"score": 4, "description": "口感顺滑"},
                    "balance": {"score": 4, "description": "整体平衡"},
                },
                "notes": "甜感不错",
            },
            "raw_input": "今天用 V60 和 C40 #19 冲了千峰庄园帕卡马拉，15g，225ml，93度，甜感不错",
        },
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["brew_id"].startswith("brew_")
    assert first_payload["trace_id"].startswith("brew_confirm_")
    record_id = first_payload["brew_id"]

    second = client.post(
        "/v1/brew/confirm",
        headers=headers,
        json={
            "bean_card_id": bean_id,
            "draft": {
                "bean_name": "千峰庄园 帕卡马拉 CM 日晒",
                "device": "V60",
                "grinder": "C40 #18",
                "grind_setting": "#18",
                "dose_g": 15,
                "water_ml": 225,
                "water_temp_c": 92,
                "brew_time_seconds": 150,
                "evaluation": {
                    "overall": {"score": 3, "description": "酸感偏突出"},
                    "acidity": {"score": 4, "description": "酸质明显"},
                    "balance": {"score": 3, "description": "平衡稍弱"},
                },
                "notes": "酸感更明显",
            },
        },
    )
    assert second.status_code == 200

    quota = client.get("/v1/me/quota", headers=headers)
    assert quota.status_code == 200
    assert quota.json()["ai_used"] == 3
    assert "records_used" not in quota.json()

    listed = client.get("/v1/brew/records", headers=headers, params={"bean": "千峰庄园"})
    assert listed.status_code == 200
    listed_payload = listed.json()
    assert listed_payload["total"] == 2
    assert listed_payload["items"][0]["bean_name"] == "千峰庄园 帕卡马拉 CM 日晒"

    detail = client.get(f"/v1/brew/records/{record_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["ratio"] == "1:15"
    assert detail.json()["ratio_value"] == 15
    assert detail.json()["brew_time_seconds"] == 155

    updated = client.patch(
        f"/v1/brew/records/{record_id}",
        headers=headers,
        json={"evaluation": {"overall": {"score": 5, "description": "甜感更集中"}}, "notes": "甜感更集中"},
    )
    assert updated.status_code == 200
    assert updated.json()["evaluation"]["overall"]["score"] == 5
    assert updated.json()["notes"] == "甜感更集中"

    compared = client.get("/v1/brew/compare", headers=headers, params={"bean_name": "千峰庄园"})
    assert compared.status_code == 200
    compared_payload = compared.json()
    assert len(compared_payload) == 2
    assert compared_payload[0]["bean_name"] == "千峰庄园 帕卡马拉 CM 日晒"
    assert compared_payload[0]["overall_score"] is None

    deleted = client.delete(f"/v1/brew/records/{record_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    missing = client.get(f"/v1/brew/records/{record_id}", headers=headers)
    assert missing.status_code == 404


def test_brew_confirm_rejects_incomplete_draft_without_charging_quota() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:brew-user-missing:brew@example.com"}
    bean_id = _confirm_test_bean(client, headers)

    response = client.post("/v1/brew/confirm", headers=headers, json={"bean_card_id": bean_id, "draft": {}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "brew_ratio_fields_incomplete"

    quota = client.get("/v1/me/quota", headers=headers)
    assert quota.status_code == 200
    assert quota.json()["ai_used"] == 0


def test_brew_confirm_rejects_legacy_top_level_score() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:brew-user-legacy-score:brew@example.com"}
    bean_id = _confirm_test_bean(client, headers)

    response = client.post(
        "/v1/brew/confirm",
        headers=headers,
        json={
            "bean_card_id": bean_id,
            "draft": {
                "bean_name": "翡翠庄园 瑰夏 水洗",
                "device": "V60",
                "grinder": "C40",
                "grind_setting": "#20",
                "dose_g": 15,
                "water_ml": 240,
                "water_temp_c": 94,
                "brew_time_seconds": 170,
            },
            "score": 4,
        },
    )
    assert response.status_code == 422


def test_manual_brew_record_keeps_bean_rating_and_brew_score_separate() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:manual-brew-user:brew@example.com"}
    bean_id = _confirm_test_bean(client, headers)

    created = client.post(
        "/v1/brew/records",
        headers=headers,
        json={
            "bean_card_id": bean_id,
            "brew_method": "滤杯冲煮",
            "device": "V60",
            "grinder": "ZP6S",
            "filter_media": "纸滤",
            "water": "农夫山泉",
            "dose_g": 15,
            "water_ml": 240,
            "water_temp_c": 92,
            "brew_time_seconds": 150,
            "bean_rating": {"overall": {"score": 4}, "aroma": {"score": 3}},
            "brew_score": 5,
            "notes": "表单新增，不走 AI",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["source_type"] == "manual"
    assert body["raw_input"] is None
    assert body["ratio"] == "1:16"
    assert body["bean_rating"]["overall"]["score"] == 4
    assert body["brew_score"] == 5
    first_id = body["id"]

    quota = client.get("/v1/me/quota", headers=headers)
    assert quota.status_code == 200
    assert quota.json()["ai_used"] == 0

    bean = client.get(f"/v1/beans/{bean_id}", headers=headers)
    assert bean.status_code == 200
    assert bean.json()["rating"]["overall"]["score"] == 4
    assert bean.json()["avg_score"] == 4

    second = client.post(
        "/v1/brew/records",
        headers=headers,
        json={
            "bean_card_id": bean_id,
            "device": "V60",
            "grinder": "ZP6S",
            "filter_media": "纸滤",
            "water": "农夫山泉",
            "notes": "只记录描述，也可以保存",
        },
    )
    assert second.status_code == 200, second.text
    second_id = second.json()["id"]

    updated = client.patch(
        f"/v1/brew/records/{first_id}",
        headers=headers,
        json={
            "dose_g": 20,
            "water_ml": 300,
            "bean_rating": {"overall": {"score": 3}, "balance": {"score": 4}},
            "brew_score": 2,
        },
    )
    assert updated.status_code == 200, updated.text
    updated_body = updated.json()
    assert updated_body["ratio"] == "1:15"
    assert updated_body["bean_rating"]["overall"]["score"] == 3
    assert updated_body["brew_score"] == 2

    second_detail = client.get(f"/v1/brew/records/{second_id}", headers=headers)
    assert second_detail.status_code == 200
    assert second_detail.json()["bean_rating"]["overall"]["score"] == 3
    assert second_detail.json()["brew_score"] is None

    equipment = client.get("/v1/equipment", headers=headers)
    assert equipment.status_code == 200
    items = equipment.json()
    assert len([item for item in items if item["category"] == "brewer" and item["name"] == "V60"]) == 1
    assert len([item for item in items if item["category"] == "grinder" and item["name"] == "ZP6S"]) == 1


def test_manual_brew_record_requires_linked_bean_card() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:manual-brew-missing-bean:brew@example.com"}

    missing = client.post("/v1/brew/records", headers=headers, json={"notes": "没有豆卡"})
    assert missing.status_code == 422

    invalid = client.post(
        "/v1/brew/records",
        headers=headers,
        json={"bean_card_id": "bean_missing", "notes": "不存在的豆卡"},
    )
    assert invalid.status_code == 404
    assert invalid.json()["error"]["code"] == "bean_not_found"


def test_brew_confirm_completes_ratio_fields_from_any_two_values() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:brew-user-ratio:brew@example.com"}
    bean_id = _confirm_test_bean(client, headers, name="翡翠庄园 瑰夏 水洗")

    dose_and_ratio = client.post(
        "/v1/brew/confirm",
        headers=headers,
        json={
            "bean_card_id": bean_id,
            "draft": {
                "bean_name": "翡翠庄园 瑰夏 水洗",
                "device": "V60",
                "grinder": "C40",
                "grind_setting": "#20",
                "dose_g": 15,
                "ratio": "1:16",
                "water_temp_c": 94,
                "brew_time_seconds": 170,
            }
        },
    )
    assert dose_and_ratio.status_code == 200
    first_id = dose_and_ratio.json()["brew_id"]
    first_record = client.get(f"/v1/brew/records/{first_id}", headers=headers)
    assert first_record.status_code == 200
    assert first_record.json()["water_ml"] == 240
    assert first_record.json()["ratio_value"] == 16

    water_and_ratio = client.post(
        "/v1/brew/confirm",
        headers=headers,
        json={
            "bean_card_id": bean_id,
            "draft": {
                "bean_name": "翡翠庄园 瑰夏 水洗",
                "device": "V60",
                "grinder": "C40",
                "grind_setting": "#21",
                "water_ml": 255,
                "ratio": "1:17",
                "water_temp_c": 93,
                "brew_time_seconds": 180,
            }
        },
    )
    assert water_and_ratio.status_code == 200
    second_id = water_and_ratio.json()["brew_id"]
    second_record = client.get(f"/v1/brew/records/{second_id}", headers=headers)
    assert second_record.status_code == 200
    assert second_record.json()["dose_g"] == 15
    assert second_record.json()["ratio"] == "1:17"


def test_peer_brew_records_require_pro_and_return_anonymous_same_bean_records() -> None:
    client = TestClient(create_app())
    source_headers = {"Authorization": "Bearer dev:peer-source:source@example.com"}
    viewer_headers = {"Authorization": "Bearer dev:peer-viewer:viewer@example.com"}

    source_bean_id = _confirm_test_bean(client, source_headers, name="同豆参考测试 瑰夏 水洗")
    viewer_bean_id = _confirm_test_bean(client, viewer_headers, name="同豆参考测试 瑰夏 水洗")

    created = client.post(
        "/v1/brew/records",
        headers=source_headers,
        json={
            "bean_card_id": source_bean_id,
            "device": "V60",
            "grinder": "C40",
            "dose_g": 15,
            "water_ml": 240,
            "water_temp_c": 92,
            "brew_time_seconds": 155,
            "brew_score": 4,
            "notes": "源用户自己的备注，不应返回给其他用户",
        },
    )
    assert created.status_code == 200, created.text

    denied = client.get("/v1/brew/records/peer", headers=viewer_headers, params={"bean_card_id": viewer_bean_id})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "upgrade_required"

    _set_plan("peer-viewer", "pro")
    peers = client.get("/v1/brew/records/peer", headers=viewer_headers, params={"bean_card_id": viewer_bean_id})
    assert peers.status_code == 200, peers.text
    body = peers.json()
    assert len(body) == 1
    assert body[0]["bean_name"] == "同豆参考测试 瑰夏 水洗"
    assert body[0]["device"] == "V60"
    assert body[0]["brew_score"] == 4
    assert "user_id" not in body[0]
    assert "raw_input" not in body[0]
    assert "notes" not in body[0]
    assert "trace_id" not in body[0]
