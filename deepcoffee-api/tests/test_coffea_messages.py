from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

HEADERS = {"Authorization": "Bearer dev:coffea-user-1:coffea@example.com"}


def test_message_creates_session_and_routes_local() -> None:
    # 测试环境无模型网关 → 调度走本地兜底，source=local。
    client = TestClient(create_app())
    resp = client.post(
        "/v1/coffea/messages",
        headers=HEADERS,
        json={"message": "瑰夏为什么有花香？"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "local"
    assert body["primary_intent"] == "knowledge_answer"
    assert body["session_id"].startswith("sess_")
    assert body["trace_id"].startswith("coffea_dispatch_")
    assert "state" in body
    # 知识库问答已真执行：results 里有一条 done 的 knowledge_answer（本地降级，无模型网关）。
    kb_results = [r for r in body["results"] if r["type"] == "knowledge_answer"]
    assert kb_results and kb_results[0]["status"] == "done"
    assert kb_results[0]["message"]


def test_image_message_degrades_without_vision_channel() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/v1/coffea/messages",
        headers=HEADERS,
        json={"message": "帮我看看这张豆卡", "attachments": [{"type": "image", "ref": "img_1"}]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["primary_intent"] == "read_bean_card_image"
    img_results = [r for r in body["results"] if r["type"] == "read_bean_card_image"]
    # 未配 vision 通道 → 图片动作降级，提示用户贴文字。
    assert img_results and img_results[0]["status"] == "degraded"


def test_session_continuity() -> None:
    client = TestClient(create_app())
    first = client.post("/v1/coffea/messages", headers=HEADERS, json={"message": "在吗"})
    sid = first.json()["session_id"]
    second = client.post(
        "/v1/coffea/messages",
        headers=HEADERS,
        json={"message": "网上对这支豆评价如何", "session_id": sid},
    )
    assert second.status_code == 200, second.text
    assert second.json()["session_id"] == sid
    assert second.json()["primary_intent"] == "web_verify"


def test_unknown_session_id_gets_fresh_session() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/v1/coffea/messages",
        headers=HEADERS,
        json={"message": "你好", "session_id": "sess_does_not_exist"},
    )
    assert resp.status_code == 200, resp.text
    # 未知 session_id 不被抢占，分配一个新的服务端 id。
    assert resp.json()["session_id"] != "sess_does_not_exist"
    assert resp.json()["session_id"].startswith("sess_")


def test_image_attachment_routes_to_image_understanding() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/v1/coffea/messages",
        headers=HEADERS,
        json={"message": "帮我看看这张豆卡", "attachments": [{"type": "image", "ref": "img_1"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["primary_intent"] == "read_bean_card_image"


def test_empty_message_rejected() -> None:
    client = TestClient(create_app())
    resp = client.post("/v1/coffea/messages", headers=HEADERS, json={"message": ""})
    assert resp.status_code == 422


def test_requires_auth() -> None:
    client = TestClient(create_app())
    resp = client.post("/v1/coffea/messages", json={"message": "hi"})
    assert resp.status_code == 401


def test_message_hydrates_user_context_without_error() -> None:
    # 有真豆子数据时，端点会 list 豆子并 model_dump(mode="json") 喂调度器（含 datetime / 嵌套 flavor）。
    # 验证水合 + 序列化路径在真数据下不报错。
    client = TestClient(create_app())
    confirmed = client.post(
        "/v1/beans/confirm",
        headers=HEADERS,
        json={
            "draft": {
                "name": "千峰庄园 瑰夏 日晒",
                "origin_name": "巴拿马",
                "process_name": "日晒",
                "varietal_names": ["瑰夏"],
            }
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    resp = client.post("/v1/coffea/messages", headers=HEADERS, json={"message": "随便问一句"})
    assert resp.status_code == 200, resp.text


def test_knowledge_answer_bubbles_to_top_level() -> None:
    # coffea 一站式返回：知识问答答案应同时出现在最外层 reply，
    # 前端读这个主回复字段即可显示，无需遍历 results 或二次调 /knowledge/ask。
    client = TestClient(create_app())
    resp = client.post("/v1/coffea/messages", headers=HEADERS, json={"message": "瑰夏为什么有花香？"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    kb = [r for r in body["results"] if r["type"] == "knowledge_answer" and r["status"] == "done"]
    assert kb
    assert body["reply"]
    assert body["reply"] == kb[0]["message"]
    assert "user_visible_message" not in body


# ── 豆卡识图收尾：高识别度自动录入 / 低识别度草稿确认 / 同名防重 ──

def _fake_vision(monkeypatch, data):  # noqa: ANN001
    from app.services import coffea_executor as ce

    async def fake_understand_image(**kwargs):  # noqa: ANN003
        return data

    monkeypatch.setattr(ce, "understand_image", fake_understand_image)


_FULL_BEAN_FIELDS = {
    "name": "自动录入测试豆",
    "roaster_name": "Coffeebuff",
    "origin_name": "巴拿马",
    "process_name": "CM 日晒",
    "varietal_names": ["帕卡马拉"],
}
_IMG_ATTACH = {"attachments": [{"type": "image", "ref": "img_1"}]}


def test_high_confidence_bean_card_auto_saves(monkeypatch) -> None:  # noqa: ANN001
    _fake_vision(monkeypatch, {
        "image_type": "bean_card",
        "confidence": 0.9,
        "ocr_text": ["自动录入测试豆", "Coffeebuff"],
        "bean_fields": _FULL_BEAN_FIELDS,
    })
    headers = {"Authorization": "Bearer dev:bean-auto-1:bean-auto-1@example.com"}
    client = TestClient(create_app())
    resp = client.post(
        "/v1/coffea/messages", headers=headers,
        json={"message": "给我录入这个豆子", **_IMG_ATTACH},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "已识别并录入" in body["reply"] and "自动录入测试豆" in body["reply"]
    img = next(r for r in body["results"] if r["type"] == "read_bean_card_image")
    assert img["output"]["auto_saved"] is True
    bean_id = img["output"]["bean_id"]
    # 原始判定字段不下发
    assert "draft" not in img["output"] and "auto_save_eligible" not in img["output"]
    # 会话 active_bean_id 指向新豆；豆仓里真的有这支豆
    assert body["state"]["active_bean_id"] == bean_id
    beans = client.get("/v1/beans", headers=headers).json()
    assert any(b["bean_id"] == bean_id for b in beans["items"])


def test_low_confidence_bean_card_returns_draft_for_confirm(monkeypatch) -> None:  # noqa: ANN001
    _fake_vision(monkeypatch, {
        "image_type": "bean_card",
        "confidence": 0.9,  # 自报高但字段不全 → 综合识别度低 → 草稿确认
        "bean_fields": {"name": "信息不全豆"},
    })
    headers = {"Authorization": "Bearer dev:bean-draft-1:bean-draft-1@example.com"}
    client = TestClient(create_app())
    resp = client.post(
        "/v1/coffea/messages", headers=headers,
        json={"message": "给我录入这个豆子", **_IMG_ATTACH},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "草稿卡" in body["reply"]
    img = next(r for r in body["results"] if r["type"] == "read_bean_card_image")
    assert img["output"]["draft"]["name"] == "信息不全豆"
    assert img["output"]["auto_save_eligible"] is False
    # 不自动建档
    beans = client.get("/v1/beans", headers=headers).json()
    assert beans["total"] == 0


def test_duplicate_bean_name_blocks_auto_save(monkeypatch) -> None:  # noqa: ANN001
    _fake_vision(monkeypatch, {
        "image_type": "bean_card",
        "confidence": 0.9,
        "bean_fields": _FULL_BEAN_FIELDS,
    })
    headers = {"Authorization": "Bearer dev:bean-dup-1:bean-dup-1@example.com"}
    client = TestClient(create_app())
    first = client.post(
        "/v1/beans/confirm", headers=headers,
        json={"draft": {"name": "自动录入测试豆"}, "source_type": "text"},
    )
    assert first.status_code == 200, first.text
    resp = client.post(
        "/v1/coffea/messages", headers=headers,
        json={"message": "给我录入这个豆子", **_IMG_ATTACH},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "同名" in body["reply"]
    img = next(r for r in body["results"] if r["type"] == "read_bean_card_image")
    assert img["output"]["auto_save_eligible"] is False
    assert img["output"]["draft"]["name"] == "自动录入测试豆"
    beans = client.get("/v1/beans", headers=headers).json()
    assert beans["total"] == 1


def test_non_bean_image_degrades_with_manual_entry_hint(monkeypatch) -> None:  # noqa: ANN001
    _fake_vision(monkeypatch, {"image_type": "brew_photo", "brew_photo_assessment": {}})
    headers = {"Authorization": "Bearer dev:bean-wrong-1:bean-wrong-1@example.com"}
    client = TestClient(create_app())
    resp = client.post(
        "/v1/coffea/messages", headers=headers,
        json={"message": "给我录入这个豆子", **_IMG_ATTACH},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "不像豆卡" in body["reply"] and "手动录入" in body["reply"]
    img = next(r for r in body["results"] if r["type"] == "read_bean_card_image")
    assert img["status"] == "degraded"


def test_provider_quota_degrade_appends_notice(monkeypatch) -> None:  # noqa: ANN001
    """服务端模型 key 配额/欠费降级时，reply 末尾必须出现显式提示（而非静默变笨）。"""
    from app.schemas.coffea import DispatchPlan
    from app.services import coffea_dispatch as cd

    async def fake_dispatch(**kwargs):  # noqa: ANN003
        return DispatchPlan(
            primary_intent="ask_clarification",
            actions=[],
            direct_reply="可以多说一点吗？",
            source="local",
            degrade_reason="provider_quota",
        )

    monkeypatch.setattr(cd, "dispatch", fake_dispatch)
    client = TestClient(create_app())
    resp = client.post("/v1/coffea/messages", headers=HEADERS, json={"message": "随便聊聊"})
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert reply.endswith("AI 服务暂时不可用，本次为基础回复。")
    assert "可以多说一点吗" in reply


def test_quota_counts_one_per_message_despite_detail_events(monkeypatch) -> None:  # noqa: ANN001
    """一条消息会记 dispatch + 能力明细 + autosave 多条事件，但月额度只计入口 1 次。"""
    _fake_vision(monkeypatch, {
        "image_type": "bean_card",
        "confidence": 0.9,
        "bean_fields": _FULL_BEAN_FIELDS,
    })
    headers = {"Authorization": "Bearer dev:bean-billing-1:bean-billing-1@example.com"}
    client = TestClient(create_app())
    resp = client.post(
        "/v1/coffea/messages", headers=headers,
        json={"message": "给我录入这个豆子", **_IMG_ATTACH},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"]  # 真执行了能力（产生明细事件）
    quota = client.get("/v1/me/quota", headers=headers).json()
    assert quota["ai_used"] == 1


# ── 会话跨设备同步：GET /coffea/session 返回双向历史 ──

def test_session_history_round_trips_across_devices() -> None:
    headers = {"Authorization": "Bearer dev:sync-user-1:sync-user-1@example.com"}
    # 设备 A：发两轮
    client_a = TestClient(create_app())
    r1 = client_a.post("/v1/coffea/messages", headers=headers, json={"message": "瑰夏为什么有花香"})
    assert r1.status_code == 200, r1.text
    sid = r1.json()["session_id"]
    r2 = client_a.post("/v1/coffea/messages", headers=headers, json={"message": "那耶加雪菲呢", "session_id": sid})
    assert r2.status_code == 200, r2.text

    # 设备 B：全新 client（同 token），拉历史应看到 A 聊的内容
    client_b = TestClient(create_app())
    hist = client_b.get("/v1/coffea/session", headers=headers)
    assert hist.status_code == 200, hist.text
    body = hist.json()
    assert body["session_id"] == sid  # 同一条永久对话
    roles = [t["role"] for t in body["turns"]]
    texts = [t["text"] for t in body["turns"]]
    assert roles.count("user") == 2 and "assistant" in roles
    assert "瑰夏为什么有花香" in texts and "那耶加雪菲呢" in texts
    # assistant 轮带 results 摘要（知识问答），且无草稿/原图大字段
    assistant_turns = [t for t in body["turns"] if t["role"] == "assistant"]
    assert assistant_turns and assistant_turns[0]["text"]


def test_session_history_empty_for_new_user() -> None:
    headers = {"Authorization": "Bearer dev:sync-fresh-1:sync-fresh-1@example.com"}
    client = TestClient(create_app())
    hist = client.get("/v1/coffea/session", headers=headers)
    assert hist.status_code == 200, hist.text
    body = hist.json()
    assert body["session_id"].startswith("sess_")
    assert body["turns"] == []


# ── 识图建卡后按默认器具给冲煮建议 ──

def test_wants_brew_plan_detection() -> None:
    from app.api.v1.coffea import _wants_brew_plan
    assert _wants_brew_plan("这个豆子给我一个热冲方案")
    assert _wants_brew_plan("怎么冲比较好")
    assert not _wants_brew_plan("帮我建个豆卡")


def test_image_bean_with_brew_intent_no_equipment_prompts_for_equipment(monkeypatch) -> None:  # noqa: ANN001
    _fake_vision(monkeypatch, {
        "image_type": "bean_card",
        "confidence": 0.9,
        "bean_fields": _FULL_BEAN_FIELDS,
    })
    headers = {"Authorization": "Bearer dev:brew-advice-1:brew-advice-1@example.com"}
    client = TestClient(create_app())
    resp = client.post(
        "/v1/coffea/messages", headers=headers,
        json={"message": "这个豆子给我一个热冲方案", **_IMG_ATTACH},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert "已识别并录入" in reply  # 建卡照常
    assert "默认器具" in reply and "我的器具" in reply  # 无器具 → 引导补


def test_chat_images_uploaded_and_in_history(monkeypatch) -> None:  # noqa: ANN001
    """带图消息：图片上传图床得 URL，存进用户轮，GET /session 跨设备能取回。"""
    from app.api.v1 import coffea as coffea_mod

    async def fake_upload(attachments, *, user_id, settings):  # noqa: ANN001, ANN003
        return [f"https://stub.supabase.co/storage/v1/object/public/chat-images/{user_id}/x.jpg"]

    monkeypatch.setattr(coffea_mod, "upload_chat_images", fake_upload)
    headers = {"Authorization": "Bearer dev:imgstore-1:imgstore-1@example.com"}
    client = TestClient(create_app())
    resp = client.post(
        "/v1/coffea/messages", headers=headers,
        json={"message": "看看这张图", "attachments": [{"type": "image", "data_url": "data:image/jpeg;base64,/9j/x"}]},
    )
    assert resp.status_code == 200, resp.text
    hist = client.get("/v1/coffea/session", headers=headers).json()
    user_turn = next(t for t in hist["turns"] if t["role"] == "user")
    assert user_turn["images"] and user_turn["images"][0].endswith("x.jpg")


def test_text_only_message_has_no_images() -> None:
    headers = {"Authorization": "Bearer dev:noimg-1:noimg-1@example.com"}
    client = TestClient(create_app())
    resp = client.post("/v1/coffea/messages", headers=headers, json={"message": "你好"})
    assert resp.status_code == 200, resp.text
    hist = client.get("/v1/coffea/session", headers=headers).json()
    user_turn = next(t for t in hist["turns"] if t["role"] == "user")
    assert user_turn["images"] == []


# ── 主动冲煮记录 + 单件器具草稿 ──

def _result(body: dict, type_: str) -> list[dict]:
    return [r for r in body["results"] if r["type"] == type_]


def test_brew_description_returns_brew_and_equipment_drafts() -> None:
    headers = {"Authorization": "Bearer dev:brew-draft-1:brew-draft-1@example.com"}
    client = TestClient(create_app())
    resp = client.post(
        "/v1/coffea/messages",
        headers=headers,
        json={"message": "今天用 V60 冲了巴拿马瑰夏，15g 粉，225ml，93°C，2:40，ZP6S 5.0 圈，纸滤。"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    brew = _result(body, "brew_record_parse")
    assert brew and brew[0]["output"]["draft"]["device"] == "V60"
    assert brew[0]["output"]["draft"]["grinder"] == "ZP6S"
    assert brew[0]["output"]["draft"]["filter_media"] == "纸滤"
    assert brew[0]["output"]["draft"]["dose_g"] == 15
    equipment = _result(body, "equipment_capture")
    assert equipment
    assert {"category": "brewer", "name": "V60"} in equipment[0]["output"]["items"]
    assert {"category": "grinder", "name": "ZP6S"} in equipment[0]["output"]["items"]


def test_record_this_brew_uses_recent_dialog_context() -> None:
    headers = {"Authorization": "Bearer dev:brew-context-1:brew-context-1@example.com"}
    client = TestClient(create_app())
    first = client.post(
        "/v1/coffea/messages",
        headers=headers,
        json={"message": "刚才用 V60 冲了一杯，15g 粉，225ml 水，93°C，总时间 2:40，ZP6S 5 圈。"},
    )
    assert first.status_code == 200, first.text
    sid = first.json()["session_id"]
    second = client.post(
        "/v1/coffea/messages",
        headers=headers,
        json={"message": "帮我记录这次冲煮", "session_id": sid},
    )
    assert second.status_code == 200, second.text
    brew = _result(second.json(), "brew_record_parse")
    assert brew
    draft = brew[0]["output"]["draft"]
    assert draft["device"] == "V60"
    assert draft["grinder"] == "ZP6S"
    assert draft["dose_g"] == 15
    assert draft["water_ml"] == 225


def test_session_result_patch_preserves_saved_card_state() -> None:
    headers = {"Authorization": "Bearer dev:card-state-1:card-state-1@example.com"}
    client = TestClient(create_app())
    resp = client.post(
        "/v1/coffea/messages",
        headers=headers,
        json={"message": "今天用 V60 冲了巴拿马瑰夏，15g 粉，225ml，93°C，2:40，ZP6S 5.0 圈，纸滤。"},
    )
    assert resp.status_code == 200, resp.text
    brew = _result(resp.json(), "brew_record_parse")[0]
    ui_state_id = brew["output"]["ui_state_id"]

    patched = client.patch(
        "/v1/coffea/session/result",
        headers=headers,
        json={
            "ui_state_id": ui_state_id,
            "patch": {"saved_record_id": "brew_saved_for_ui", "saved_recap": "已保存这杯。"},
            "message": "已保存到冲煮记录。",
        },
    )
    assert patched.status_code == 200, patched.text

    hist = client.get("/v1/coffea/session", headers=headers).json()
    assistant = next(t for t in hist["turns"] if t["role"] == "assistant")
    saved = next(r for r in assistant["results"] if r.get("output", {}).get("ui_state_id") == ui_state_id)
    assert saved["output"]["draft"]["device"] == "V60"
    assert saved["output"]["saved_record_id"] == "brew_saved_for_ui"
    assert saved["message"] == "已保存到冲煮记录。"

    repeat = client.post(
        "/v1/coffea/messages",
        headers=headers,
        json={"message": "帮我记录这次冲煮", "session_id": resp.json()["session_id"]},
    )
    assert repeat.status_code == 200, repeat.text
    repeated_brew = _result(repeat.json(), "brew_record_parse")
    assert repeated_brew
    assert "已经保存" in repeated_brew[0]["message"]
    assert not (repeated_brew[0].get("output") or {}).get("draft")


def test_equipment_capture_uses_recent_dialog_when_user_only_says_save() -> None:
    headers = {"Authorization": "Bearer dev:eq-context-save-1:eq-context-save-1@example.com"}
    client = TestClient(create_app())
    first = client.post(
        "/v1/coffea/messages",
        headers=headers,
        json={"message": "我现在用 ZP6S，也常用农夫山泉。"},
    )
    assert first.status_code == 200, first.text
    sid = first.json()["session_id"]

    second = client.post(
        "/v1/coffea/messages",
        headers=headers,
        json={"message": "要存", "session_id": sid},
    )
    assert second.status_code == 200, second.text
    equipment = _result(second.json(), "equipment_capture")
    assert equipment
    items = equipment[0]["output"]["items"]
    assert {"category": "grinder", "name": "ZP6S"} in items
    assert {"category": "water", "name": "农夫山泉"} in items


def test_equipment_capture_only_when_user_owns_or_saves() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:eq-chat-1:eq-chat-1@example.com"}
    owned = client.post("/v1/coffea/messages", headers=headers, json={"message": "我新买了法压壶，帮我存一下"})
    assert owned.status_code == 200, owned.text
    equipment = _result(owned.json(), "equipment_capture")
    assert equipment
    assert {"category": "brewer", "name": "法压壶"} in equipment[0]["output"]["items"]

    question = client.post("/v1/coffea/messages", headers=headers, json={"message": "法压壶怎么用？"})
    assert question.status_code == 200, question.text
    assert _result(question.json(), "equipment_capture") == []
    assert question.json()["primary_intent"] == "knowledge_answer"


def test_existing_equipment_does_not_return_duplicate_capture_card() -> None:
    headers = {"Authorization": "Bearer dev:eq-chat-dedupe-1:eq-chat-dedupe-1@example.com"}
    client = TestClient(create_app())
    saved = client.post("/v1/equipment", headers=headers, json={"category": "grinder", "name": "ZP6S"})
    assert saved.status_code == 200, saved.text
    resp = client.post("/v1/coffea/messages", headers=headers, json={"message": "我用 ZP6S"})
    assert resp.status_code == 200, resp.text
    equipment = _result(resp.json(), "equipment_capture")
    assert equipment == [] or all(not r.get("output") or not r["output"].get("items") for r in equipment)
