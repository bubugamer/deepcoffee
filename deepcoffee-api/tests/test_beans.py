from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.core.db import get_sessionmaker
from app.main import create_app
from app.models.tables import UserEquipmentProfile

HEADERS = {"Authorization": "Bearer dev:bean-user-1:bean@example.com"}


def _seed_equipment(user_id: str, brew_method: str = "V60", grinder: str = "Comandante C40", filter_media: str = "Hario V60 滤纸") -> None:
    """直接塞一套完整器具资料（用户档案需已存在，先调一次端点即可）。"""

    async def _do() -> None:
        sm = get_sessionmaker()
        async with sm() as session:
            session.add(
                UserEquipmentProfile(
                    id="eq_seed_1",
                    user_id=user_id,
                    brew_method=brew_method,
                    grinder=grinder,
                    filter_media=filter_media,
                )
            )
            await session.commit()

    asyncio.run(_do())


def _confirm_bean(client: TestClient, name: str = "千峰庄园 瑰夏 日晒") -> str:
    resp = client.post(
        "/v1/beans/confirm",
        headers=HEADERS,
        json={
            "draft": {
                "name": name,
                "roaster_name": "千峰",
                "origin_name": "巴拿马",
                "process_name": "日晒",
                "varietal_names": ["瑰夏"],
            }
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["bean_id"]


def test_bean_parse_returns_default_flavor_template() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/v1/beans/parse",
        headers=HEADERS,
        json={"input": "巴拿马 千峰庄园 瑰夏 日晒，茉莉花香、柑橘"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    draft = body["draft"]
    assert draft["origin_name"] == "巴拿马"
    assert draft["process_name"] == "日晒"
    assert "瑰夏" in draft["varietal_names"]
    # 默认动态风味维度（5 根轴）。
    assert len(draft["flavor"]["axes"]) == 5
    assert "茉莉" in draft["flavor"]["notes"]
    assert body["trace_id"].startswith("bean_parse_")


def test_bean_confirm_list_detail_and_flavor_update() -> None:
    client = TestClient(create_app())
    bean_id = _confirm_bean(client)

    listed = client.get("/v1/beans", headers=HEADERS)
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1
    assert any(item["bean_id"] == bean_id for item in listed.json()["items"])

    detail = client.get(f"/v1/beans/{bean_id}", headers=HEADERS)
    assert detail.status_code == 200
    assert detail.json()["process"] == "日晒"
    assert detail.json()["record_count"] == 0
    assert detail.json()["avg_score"] is None

    # 用户补填风味强度（官方缺失时）。
    updated = client.patch(
        f"/v1/beans/{bean_id}",
        headers=HEADERS,
        json={
            "flavor": {
                "notes": ["茉莉花香", "柑橘"],
                "source": "user",
                "scale_max": 5,
                "axes": [{"label": "酸质", "value": 4}, {"label": "甜感", "value": 5}],
            }
        },
    )
    assert updated.status_code == 200
    assert updated.json()["flavor"]["source"] == "user"
    assert updated.json()["flavor"]["axes"][1]["value"] == 5


def test_recommend_params_needs_equipment_then_completes() -> None:
    # 多轮契约（§5）。测试环境无 new-api → 模型不可用，走本地兜底分支。
    client = TestClient(create_app())
    bean_id = _confirm_bean(client)

    # 无器具 + 无模型 → fallback，不落库。
    first = client.post(f"/v1/beans/{bean_id}/recommend-params", headers=HEADERS, json={})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "fallback"
    assert first.json()["recommended_record_id"] is None
    assert first.json()["missing_fields"]  # 提示缺哪些器具
    session_id = first.json()["session_id"]
    assert session_id.startswith("sess_")

    # 用户已存一套完整器具 → 本地兜底直接 completed，落隐藏 ai_suggestion 记录。
    _seed_equipment("bean-user-1")
    second = client.post(
        f"/v1/beans/{bean_id}/recommend-params",
        headers=HEADERS,
        json={"session_id": session_id, "message": "就用这套"},
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["status"] == "completed"
    assert body["source"] == "local"
    assert body["recommended_record_id"]
    assert body["recommendation"]["device"] == "V60"
    assert body["recommendation"]["water_ml"] is not None  # 已由粉量+粉水比换算

    # ai_suggestion 记录用户不可见：不进冲煮记录列表。
    records = client.get("/v1/brew/records", headers=HEADERS)
    assert records.status_code == 200
    assert records.json()["total"] == 0

    # 豆子详情指向建议记录。
    detail = client.get(f"/v1/beans/{bean_id}", headers=HEADERS)
    assert detail.json()["recommended_record_id"] == body["recommended_record_id"]
    assert detail.json()["recommended_params"]["water_temp_c"] is not None


def test_user_record_links_to_bean_and_can_be_set_as_recommended() -> None:
    client = TestClient(create_app())
    bean_id = _confirm_bean(client, name="云南 卡蒂姆 水洗")

    confirmed = client.post(
        "/v1/brew/confirm",
        headers=HEADERS,
        json={
            "draft": {
                "bean_name": "云南 卡蒂姆 水洗",
                "device": "V60",
                "grinder": "C40",
                "grind_setting": "#20",
                "dose_g": 15,
                "water_ml": 240,
                "water_temp_c": 92,
                "brew_time_seconds": 150,
                "evaluation": {"overall": {"score": 4, "description": "干净"}},
            },
            "bean_card_id": bean_id,
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    record_id = confirmed.json()["brew_id"]

    # 该 user 记录聚合到豆子：record_count=1, avg_score=4。
    detail = client.get(f"/v1/beans/{bean_id}", headers=HEADERS)
    assert detail.json()["record_count"] == 1
    assert detail.json()["avg_score"] == 4

    # 设为建议参数 → 指针指向该用户记录。
    put = client.put(
        f"/v1/beans/{bean_id}/recommend-params",
        headers=HEADERS,
        json={"record_id": record_id},
    )
    assert put.status_code == 200, put.text
    assert put.json()["recommended_record_id"] == record_id
    assert put.json()["recommended_params"]["water_ml"] == 240


def test_brew_records_full_field_search() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:bean-search-user:bean@example.com"}
    client.post(
        "/v1/brew/confirm",
        headers=headers,
        json={
            "draft": {
                "bean_name": "耶加雪菲 科契尔",
                "origin": "埃塞俄比亚",
                "device": "V60",
                "grinder": "C40",
                "grind_setting": "#18",
                "dose_g": 15,
                "water_ml": 240,
                "water_temp_c": 92,
                "brew_time_seconds": 150,
                "notes": "柑橘明亮",
            }
        },
    )
    # q 命中 notes / origin 等非豆名字段。
    by_notes = client.get("/v1/brew/records", headers=headers, params={"q": "柑橘"})
    assert by_notes.json()["total"] == 1
    by_origin = client.get("/v1/brew/records", headers=headers, params={"q": "埃塞俄比亚"})
    assert by_origin.json()["total"] == 1
    miss = client.get("/v1/brew/records", headers=headers, params={"q": "不存在的词"})
    assert miss.json()["total"] == 0
