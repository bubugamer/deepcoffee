from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.schemas.coffea import DispatchPlan
from app.schemas.knowledge import GroundingDoc
from app.services import web_search, web_verify
from app.services.coffea_executor import execute_plan
from app.services.web_search import WebSource

_IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="


# ---------- web_search.search（Brave 客户端，mock httpx）----------


class _FakeResp:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, resp: _FakeResp) -> None:
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return self._resp


def _patch_httpx(monkeypatch, resp: _FakeResp) -> None:
    monkeypatch.setattr(web_search.httpx, "AsyncClient", lambda **k: _FakeClient(resp))


def test_search_returns_empty_without_key() -> None:
    assert asyncio.run(web_search.search("q", api_key=None, count=5)) == []


def test_search_parses_results(monkeypatch) -> None:
    payload = {
        "web": {
            "results": [
                {
                    "title": "Sey 官方",
                    "url": "https://sey.coffee",
                    "description": "<strong>high</strong> extraction",
                    "page_age": "2026-01-01",
                },
                {"title": "评测", "url": "https://x.com/r", "description": "好评"},
                {"description": "缺 url，应跳过"},
            ]
        }
    }
    _patch_httpx(monkeypatch, _FakeResp(200, payload))
    out = asyncio.run(web_search.search("sey 高萃取", api_key="bk", count=5))
    assert len(out) == 2
    assert out[0].title == "Sey 官方"
    assert out[0].snippet == "high extraction"  # HTML 标签已去
    assert out[0].published == "2026-01-01"
    assert out[1].published is None and out[1].accessed  # 无发布时间但有访问日期


def test_search_non_200_returns_empty(monkeypatch) -> None:
    _patch_httpx(monkeypatch, _FakeResp(429, {}))
    assert asyncio.run(web_search.search("q", api_key="bk")) == []


def test_build_search_query_strips_filler() -> None:
    q = web_search.build_search_query("帮我核实一下：网上对 Hario Switch 浸泡式手冲壶的最新评论和口碑怎么说？")
    assert "Hario Switch" in q
    # 口语/噪声词被剔除，聚焦产品实体。
    assert "核实" not in q and "网上" not in q and "口碑" not in q and "评论" not in q


def test_build_search_query_short_fallback() -> None:
    # 全是噪声词 → 清洗后过短 → 退回原文去标点版，避免搜空。
    assert web_search.build_search_query("怎么说？").strip() != ""


# ---------- web_verify.verify_with_model（综合层，mock gateway）----------


class _FakeGateway:
    enabled = True
    vision_enabled = True

    def __init__(self, content: str) -> None:
        self.content = content

    async def chat(self, **kwargs):  # noqa: ANN003
        return SimpleNamespace(content=self.content, model="fake")


class _SequentialGateway:
    enabled = True
    vision_enabled = True

    def __init__(self, contents: list[str]) -> None:
        self.contents = contents
        self.calls: list[dict] = []

    async def chat(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        return SimpleNamespace(content=self.contents.pop(0), model="fake")


_SOURCES = [WebSource(title="t", url="https://x", snippet="s", published=None, accessed="2026-06-05")]
_IMAGE_JSON = json.dumps(
    {
        "image_type": "bean_card",
        "ocr_text": ["SEY Coffee Pepe Jijon"],
        "bean_fields": {"roaster_name": "SEY Coffee", "name": "Pepe Jijon"},
        "confidence": 0.8,
        "uncertainties": [],
        "suggested_next_actions": ["web_verify"],
    }
)


def test_verify_returns_text_with_model() -> None:
    text = asyncio.run(
        web_verify.verify_with_model("q", _SOURCES, model="m", gateway=_FakeGateway("综合：来源说…"))
    )
    assert text == "综合：来源说…"


def test_verify_sends_images_to_vision_model() -> None:
    gw = _SequentialGateway(["综合：来源和图片一起看…"])
    text = asyncio.run(
        web_verify.verify_with_model(
            "图里这支豆口碑怎么样？",
            _SOURCES,
            model="deepseek-chat",
            image_urls=[_IMG],
            vision_model="kimi-k2.6",
            gateway=gw,
        )
    )
    assert text == "综合：来源和图片一起看…"
    assert gw.calls[0]["model"] == "kimi-k2.6"
    user_msg = gw.calls[0]["messages"][-1]
    assert isinstance(user_msg["content"], list)
    assert any(p.get("type") == "image_url" and p["image_url"]["url"] == _IMG for p in user_msg["content"])


def test_verify_none_without_sources() -> None:
    assert (
        asyncio.run(web_verify.verify_with_model("q", [], model="m", gateway=_FakeGateway("x"))) is None
    )


def test_format_sources_includes_title_and_url() -> None:
    s = web_verify.format_sources(_SOURCES)
    assert "https://x" in s and "访问于" in s


# ---------- executor _run_web_verify 三路径 ----------


class _FakeKB:
    def answer_question(self, question: str):
        return SimpleNamespace(
            answer="本地知识库摘录", from_knowledge_base=False, selected_files=[], sources=[]
        )

    def build_grounding(self, slugs, settings):  # noqa: ANN001
        return [GroundingDoc(slug="g", title="t", content="c")]


_ENABLED = SimpleNamespace(
    vision_model=None, web_search_enabled=True, brave_api_key="bk", brave_search_count=5
)
_DISABLED = SimpleNamespace(
    vision_model=None, web_search_enabled=False, brave_api_key=None, brave_search_count=5
)

_VISION_ENABLED = SimpleNamespace(
    vision_model="kimi-k2.6", web_search_enabled=True, brave_api_key="bk", brave_search_count=5
)


def _exec(monkeypatch, *, search_result, settings, gateway):
    async def fake_search(query, *, api_key, count):  # noqa: ANN001
        return search_result

    monkeypatch.setattr(web_search, "search", fake_search)
    plan = DispatchPlan(primary_intent="web_verify", actions=[{"type": "web_verify"}])
    return asyncio.run(
        execute_plan(
            plan,
            message="网上对 sey 评价如何",
            attachments=None,
            session_state={},
            knowledge_service=_FakeKB(),
            settings=settings,
            model="m",
            gateway=gateway,
        )
    )


def test_web_verify_done_with_search_and_model(monkeypatch) -> None:
    results = _exec(
        monkeypatch, search_result=_SOURCES, settings=_ENABLED, gateway=_FakeGateway("综合回答带来源")
    )
    r = results[0]
    assert r.type == "web_verify"
    assert r.status == "done"
    assert r.source == "model"
    assert r.message == "综合回答带来源"
    assert r.output["sources"]


def test_web_verify_uses_image_context_for_search_and_synthesis(monkeypatch) -> None:
    captured: dict = {}

    async def fake_search(query, *, api_key, count):  # noqa: ANN001
        captured["query"] = query
        return _SOURCES

    monkeypatch.setattr(web_search, "search", fake_search)
    gateway = _SequentialGateway([_IMAGE_JSON, "综合回答带图片线索"])
    plan = DispatchPlan(primary_intent="web_verify", actions=[{"type": "web_verify"}])
    results = asyncio.run(
        execute_plan(
            plan,
            message="帮我核实图里这支豆的口碑",
            attachments=[{"type": "image", "data_url": _IMG}],
            session_state={},
            knowledge_service=_FakeKB(),
            settings=_VISION_ENABLED,
            model="deepseek-chat",
            gateway=gateway,
        )
    )
    assert results[0].status == "done"
    assert results[0].message == "综合回答带图片线索"
    assert "SEY" in captured["query"]
    assert gateway.calls[-1]["model"] == "kimi-k2.6"
    user_msg = gateway.calls[-1]["messages"][-1]
    assert isinstance(user_msg["content"], list)
    assert any(p.get("type") == "image_url" and p["image_url"]["url"] == _IMG for p in user_msg["content"])


def test_web_verify_degrades_when_no_sources(monkeypatch) -> None:
    results = _exec(monkeypatch, search_result=[], settings=_ENABLED, gateway=_FakeGateway("x"))
    assert results[0].status == "degraded"
    assert "联网" in results[0].message


def test_web_verify_degrades_when_disabled(monkeypatch) -> None:
    # 未配 key（web_search_enabled=False）→ 直接降级，不进检索分支。
    results = _exec(monkeypatch, search_result=_SOURCES, settings=_DISABLED, gateway=_FakeGateway("x"))
    assert results[0].status == "degraded"
