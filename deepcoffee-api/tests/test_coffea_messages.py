from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

HEADERS = {"Authorization": "Bearer dev:coffea-user-1:coffea@example.com"}


def test_message_creates_session_and_routes_local() -> None:
    # 测试环境禁用 new-api → 调度走本地兜底，source=local。
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
    # 知识库问答已真执行：results 里有一条 done 的 knowledge_answer（本地降级，无 new-api）。
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


def test_balance_exhausted_notice_appended_to_reply(monkeypatch) -> None:
    """余额耗尽降级时，reply 末尾必须出现充值提示（而非静默变笨）。"""
    from app.schemas.coffea import DispatchPlan
    from app.services import coffea_dispatch as cd

    async def fake_dispatch(**kwargs):  # noqa: ANN003
        return DispatchPlan(
            primary_intent="ask_clarification",
            actions=[],
            direct_reply="可以多说一点吗？",
            source="local",
            degrade_reason="balance_exhausted",
        )

    monkeypatch.setattr(cd, "dispatch", fake_dispatch)
    client = TestClient(create_app())
    resp = client.post("/v1/coffea/messages", headers=HEADERS, json={"message": "随便聊聊"})
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert reply.endswith("AI 余额不足，本次为基础回复。请联系管理员充值。")
    assert "可以多说一点吗" in reply
