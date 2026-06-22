from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.db import get_sessionmaker
from app.main import create_app
from app.models.tables import UserEquipmentItem, UserProfile

HEADERS = {"Authorization": "Bearer dev:bean-user-1:bean@example.com"}


def _headers(user_id: str, email: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer dev:{user_id}:{email or f'{user_id}@example.com'}"}


def _set_plan(user_id: str, plan: str) -> None:
    async def _run() -> None:
        async with get_sessionmaker()() as session:
            await session.execute(update(UserProfile).where(UserProfile.id == user_id).values(plan=plan))
            await session.commit()

    asyncio.run(_run())


def _seed_equipment(user_id: str, dripper: str = "V60", grinder: str = "Comandante C40", filter_media: str = "Hario V60 滤纸") -> None:
    """直接塞默认单件器具库存（用户档案需已存在，先调一次端点即可）。"""

    async def _do() -> None:
        sm = get_sessionmaker()
        async with sm() as session:
            session.add_all([
                UserEquipmentItem(
                    id="eq_seed_brewer",
                    user_id=user_id,
                    category="brewer",
                    name=dripper,
                    normalized_name=dripper.strip().lower(),
                    is_default=True,
                ),
                UserEquipmentItem(
                    id="eq_seed_grinder",
                    user_id=user_id,
                    category="grinder",
                    name=grinder,
                    normalized_name=grinder.strip().lower(),
                    is_default=True,
                ),
                UserEquipmentItem(
                    id="eq_seed_filter",
                    user_id=user_id,
                    category="filter_media",
                    name=filter_media,
                    normalized_name=filter_media.strip().lower(),
                    is_default=True,
                ),
            ])
            await session.commit()

    asyncio.run(_do())


def _confirm_bean(client: TestClient, name: str = "千峰庄园 瑰夏 日晒", headers: dict[str, str] = HEADERS) -> str:
    resp = client.post(
        "/v1/beans/confirm",
        headers=headers,
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


def test_bean_parse_returns_flavor_without_default_axes() -> None:
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
    assert draft["flavor"]["axes"] == []
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
            "public_comment": "这支豆子适合稍低温拉甜感。",
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
    assert updated.json()["public_comment"] == "这支豆子适合稍低温拉甜感。"

    blocked = client.patch(
        f"/v1/beans/{bean_id}",
        headers=HEADERS,
        json={"name": "不应该改名"},
    )
    assert blocked.status_code == 422


def test_bean_confirm_uses_roaster_product_as_stable_name_and_saves_components() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/v1/beans/confirm",
        headers=HEADERS,
        json={
            "draft": {
                "roaster_product_name": "Bong Bong",
                "roaster_name": "coffee buff",
                "origin_name": "多产地 / 拼配",
                "process_name": "多处理法",
                "altitude_text": "1700-2300m",
                "harvest_date_text": "2026",
                "roast_date_text": "2026/05/18",
                "net_weight_text": "100g",
                "bean_components": [
                    {
                        "origin_name": "Panama Chiriqui",
                        "coffee_source_name": "Santamaria Estate",
                        "process_name": "Washed",
                        "varietal_names": ["Geisha"],
                        "altitude_text": "1800m",
                    },
                    {
                        "origin_name": "Ethiopia Oromia Guji",
                        "coffee_source_name": "Gogogu Station",
                        "process_name": "Washed",
                        "varietal_names": ["Heirloom"],
                        "altitude_text": "2100-2300m",
                    },
                ],
            }
        },
    )
    assert resp.status_code == 200, resp.text
    bean = client.get(f"/v1/beans/{resp.json()['bean_id']}", headers=HEADERS).json()
    assert bean["name"] == "Bong Bong"
    assert bean["altitude_text"] == "1700-2300m"
    assert bean["net_weight_text"] == "100g"
    assert len(bean["bean_components"]) == 2
    assert bean["bean_components"][0]["coffee_source_name"] == "Santamaria Estate"


def test_recommend_params_needs_equipment_then_completes() -> None:
    # 多轮契约（§5）。测试环境无模型网关 → 模型不可用，走本地兜底分支。
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


def test_manual_recommend_params_create_hidden_record() -> None:
    client = TestClient(create_app())
    bean_id = _confirm_bean(client, name="手动参数测试豆")
    resp = client.put(
        f"/v1/beans/{bean_id}/recommend-params",
        headers=HEADERS,
        json={"params": {
            "device": "V60", "grinder": "ZP6S", "grind_setting": "4.5–5.5 圈",
            "dose_g": 15, "water_ml": 225, "water_temp_c": 92,
            "ratio": "1:15", "brew_time_seconds": 150,
        }},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["recommended_params"]["device"] == "V60"
    assert body["recommended_params"]["record_type"] == "user_suggestion"

    # GET bean 读到手动参数；隐藏记录不进冲煮记录列表
    bean = client.get(f"/v1/beans/{bean_id}", headers=HEADERS).json()
    assert bean["recommended_params"]["grind_setting"] == "4.5–5.5 圈"
    assert bean["recommended_record_id"] == body["recommended_record_id"]
    records = client.get("/v1/brew/records", headers=HEADERS).json()
    assert all(r["id"] != body["recommended_record_id"] for r in records["items"])


def test_recommend_params_put_requires_exactly_one_of_record_or_params() -> None:
    client = TestClient(create_app())
    bean_id = _confirm_bean(client, name="参数校验豆")
    neither = client.put(f"/v1/beans/{bean_id}/recommend-params", headers=HEADERS, json={})
    assert neither.status_code == 422
    both = client.put(
        f"/v1/beans/{bean_id}/recommend-params",
        headers=HEADERS,
        json={"record_id": "brew_x", "params": {"device": "V60"}},
    )
    assert both.status_code == 422


def test_bean_square_requires_pro_and_imports_private_copy_without_private_fields() -> None:
    client = TestClient(create_app())
    source_headers = _headers("square-source", "source@example.com")
    viewer_headers = _headers("square-viewer", "viewer@example.com")
    source_id = _confirm_bean(client, name="广场测试豆 日晒", headers=source_headers)

    updated = client.patch(
        f"/v1/beans/{source_id}",
        headers=source_headers,
        json={
            "private_notes": "只有本人能看的进货渠道",
            "public_comment": "匿名评论会出现在豆仓广场。",
        },
    )
    assert updated.status_code == 200, updated.text

    assert client.get("/v1/me", headers=viewer_headers).status_code == 200
    denied = client.get("/v1/beans/square", headers=viewer_headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "upgrade_required"

    _set_plan("square-viewer", "pro")
    listed = client.get("/v1/beans/square", headers=viewer_headers)
    assert listed.status_code == 200, listed.text
    item = next(bean for bean in listed.json()["items"] if bean["bean_id"] == source_id)
    assert item["public_comment"] == "匿名评论会出现在豆仓广场。"
    assert "private_notes" not in item
    assert "user_id" not in item

    imported = client.post("/v1/beans/square/import", headers=viewer_headers, json={"bean_ids": [source_id, source_id]})
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["created_count"] == 1
    assert body["existing_count"] == 0
    imported_id = body["items"][0]["bean_id"]

    repeated = client.post("/v1/beans/square/import", headers=viewer_headers, json={"bean_ids": [source_id]})
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["created_count"] == 0
    assert repeated.json()["existing_count"] == 1
    assert repeated.json()["items"][0]["bean_id"] == imported_id

    # 副本不进广场：广场列表只剩原创豆卡，导入的副本不出现；副本的广场详情 404。
    square_after = client.get("/v1/beans/square", headers=viewer_headers)
    square_ids = [bean["bean_id"] for bean in square_after.json()["items"]]
    assert source_id in square_ids
    assert imported_id not in square_ids
    assert client.get(f"/v1/beans/square/{imported_id}", headers=viewer_headers).status_code == 404

    detail = client.get(f"/v1/beans/{imported_id}", headers=viewer_headers)
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["name"] == "广场测试豆 日晒"
    assert payload["private_notes"] is None
    assert payload["public_comment"] is None
