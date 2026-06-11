from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_brew_record_lifecycle_and_unified_ai_quota() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:brew-user-1:brew@example.com"}

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
    assert compared_payload[0]["overall_score"] in {3, 5}

    deleted = client.delete(f"/v1/brew/records/{record_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    missing = client.get(f"/v1/brew/records/{record_id}", headers=headers)
    assert missing.status_code == 404


def test_brew_confirm_rejects_incomplete_draft_without_charging_quota() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:brew-user-missing:brew@example.com"}

    response = client.post("/v1/brew/confirm", headers=headers, json={"draft": {}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "brew_ratio_fields_incomplete"

    quota = client.get("/v1/me/quota", headers=headers)
    assert quota.status_code == 200
    assert quota.json()["ai_used"] == 0


def test_brew_confirm_rejects_legacy_top_level_score() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:brew-user-legacy-score:brew@example.com"}

    response = client.post(
        "/v1/brew/confirm",
        headers=headers,
        json={
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


def test_brew_confirm_completes_ratio_fields_from_any_two_values() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:brew-user-ratio:brew@example.com"}

    dose_and_ratio = client.post(
        "/v1/brew/confirm",
        headers=headers,
        json={
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
