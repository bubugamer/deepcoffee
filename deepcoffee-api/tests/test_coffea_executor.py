from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.schemas.coffea import ActionResult, DispatchPlan
from app.schemas.knowledge import GroundingDoc
from app.services.brew_coach import LOCAL_COACH_FALLBACK
from app.services.coffea_executor import (
    _contains_brew_record_hint,
    _draft_substance_count,
    _mentions_brew_quantity,
    _official_recipe_from_bean,
    assemble_reply,
    ensure_brew_draft_result,
    ensure_equipment_capture_for_brew,
    execute_plan,
)

_IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="
_VALID_IMAGE_JSON = json.dumps({"image_type": "bean_card", "bean_fields": {"name": "巴拿马 瑰夏"}})


class _FakeKB:
    def __init__(self, *, from_kb: bool = True) -> None:
        self.from_kb = from_kb

    def answer_question(self, question: str):
        return SimpleNamespace(
            answer="本地知识库摘录答案",
            from_knowledge_base=self.from_kb,
            selected_files=[SimpleNamespace(slug="geisha")] if self.from_kb else [],
            sources=[],
        )

    def build_grounding(self, slugs, settings):  # noqa: ANN001
        return [GroundingDoc(slug="geisha", title="瑰夏", content="瑰夏以花香著称…")]


class _FakeGateway:
    enabled = True
    vision_enabled = True

    def __init__(self, content: str) -> None:
        self.content = content

    async def chat(self, **kwargs):  # noqa: ANN003
        return SimpleNamespace(content=self.content, model="fake")


_SETTINGS = SimpleNamespace(
    vision_model=None, web_search_enabled=False, brave_api_key=None, brave_search_count=5
)


def _run(plan, **overrides):
    kwargs = dict(
        message="瑰夏为什么有花香",
        attachments=None,
        session_state={},
        knowledge_service=_FakeKB(),
        settings=_SETTINGS,
        model="m",
        gateway=None,
    )
    kwargs.update(overrides)
    return asyncio.run(execute_plan(plan, **kwargs))


def test_knowledge_local_when_gateway_missing() -> None:
    plan = DispatchPlan(primary_intent="knowledge_answer", actions=[{"type": "knowledge_answer"}])
    results = _run(plan)
    assert len(results) == 1
    r = results[0]
    assert r.type == "knowledge_answer"
    assert r.status == "done"
    assert r.source == "local"
    assert r.message == "本地知识库摘录答案"


def test_knowledge_uses_model_when_gateway_available() -> None:
    plan = DispatchPlan(primary_intent="knowledge_answer", actions=[{"type": "knowledge_answer"}])
    results = _run(plan, gateway=_FakeGateway("模型生成的更自然回答"))
    r = results[0]
    assert r.status == "done"
    assert r.source == "model"
    assert r.message == "模型生成的更自然回答"


def test_knowledge_stays_local_when_not_from_kb() -> None:
    plan = DispatchPlan(primary_intent="knowledge_answer", actions=[{"type": "knowledge_answer"}])
    results = _run(plan, knowledge_service=_FakeKB(from_kb=False), gateway=_FakeGateway("x"))
    assert results[0].source == "local"


def test_knowledge_with_image_uses_model_even_without_kb_match() -> None:
    captured: dict = {}

    class _CaptureGW:
        enabled = True
        vision_enabled = True

        async def chat(self, **kwargs):  # noqa: ANN003
            captured["model"] = kwargs["model"]
            captured["user"] = kwargs["messages"][-1]["content"]
            return SimpleNamespace(content="看图后回答这款水是否适合冲咖啡", model="fake")

    plan = DispatchPlan(primary_intent="knowledge_answer", actions=[{"type": "knowledge_answer"}])
    results = _run(
        plan,
        message="这个水冲咖啡合适吗",
        attachments=[{"type": "image", "data_url": _IMG}],
        knowledge_service=_FakeKB(from_kb=False),
        settings=SimpleNamespace(vision_model="kimi-k2.6", web_search_enabled=False, brave_api_key=None, brave_search_count=5),
        gateway=_CaptureGW(),
    )
    assert results[0].source == "model"
    assert results[0].message == "看图后回答这款水是否适合冲咖啡"
    assert captured["model"] == "kimi-k2.6"
    assert any(p.get("type") == "image_url" and p["image_url"]["url"] == _IMG for p in captured["user"])


def test_image_action_degraded_without_image_bytes() -> None:
    # 附件只有文字 note、没有图片 base64 → 无图可识别 → 降级。
    plan = DispatchPlan(
        primary_intent="read_bean_card_image",
        actions=[{"type": "read_bean_card_image", "input_ref": "attachment_1"}],
    )
    results = _run(plan, attachments=[{"type": "image", "note": "巴拿马 瑰夏 日晒"}])
    assert results[0].type == "read_bean_card_image"
    assert results[0].status == "degraded"
    assert results[0].message


_VISION_SETTINGS = SimpleNamespace(vision_model="kimi-k2.6", bean_card_autosave_confidence=0.8)


def test_image_action_done_with_image_and_vision() -> None:
    plan = DispatchPlan(
        primary_intent="read_bean_card_image",
        actions=[{"type": "read_bean_card_image", "input_ref": "attachment_1"}],
    )
    results = _run(
        plan,
        attachments=[{"type": "image", "data_url": _IMG}],
        settings=_VISION_SETTINGS,
        gateway=_FakeGateway(_VALID_IMAGE_JSON),
    )
    r = results[0]
    assert r.status == "done"
    assert r.source == "model"
    # 原始识别 JSON 不透传；转成草稿 + 综合识别度 + 人话 message
    assert r.output["draft"]["name"] == "巴拿马 瑰夏"
    assert r.output["auto_save_eligible"] is False  # 只识别出豆名，完整度低
    assert r.message and "识别到" in r.message and "image_type" not in r.message


def test_bean_card_high_confidence_marks_auto_save() -> None:
    full = json.dumps({
        "image_type": "bean_card",
        "confidence": 0.92,
        "bean_fields": {
            "name": "千峰庄园 帕卡马拉",
            "roaster_name": "Coffeebuff",
            "origin_name": "巴拿马",
            "process_name": "CM 日晒",
            "varietal_names": ["帕卡马拉"],
        },
    })
    plan = DispatchPlan(
        primary_intent="read_bean_card_image",
        actions=[{"type": "read_bean_card_image", "input_ref": "attachment_1"}],
    )
    results = _run(
        plan,
        attachments=[{"type": "image", "data_url": _IMG}],
        settings=_VISION_SETTINGS,
        gateway=_FakeGateway(full),
    )
    r = results[0]
    assert r.status == "done"
    assert r.output["auto_save_eligible"] is True
    assert r.output["confidence"] == 0.92


def test_bean_card_wrong_image_type_degrades_with_manual_hint() -> None:
    plan = DispatchPlan(
        primary_intent="read_bean_card_image",
        actions=[{"type": "read_bean_card_image", "input_ref": "attachment_1"}],
    )
    results = _run(
        plan,
        attachments=[{"type": "image", "data_url": _IMG}],
        settings=_VISION_SETTINGS,
        gateway=_FakeGateway(json.dumps({"image_type": "brew_photo", "brew_photo_assessment": {}})),
    )
    r = results[0]
    assert r.status == "degraded"
    assert "不像豆卡" in r.message and "手动录入" in r.message
    assert r.output is None


def test_coach_action_local_fallback_without_gateway() -> None:
    plan = DispatchPlan(primary_intent="scale_recipe", actions=[{"type": "scale_recipe"}])
    results = _run(plan)
    assert results[0].type == "scale_recipe"
    assert results[0].status == "done"
    assert results[0].source == "local"
    assert results[0].message


def test_coach_action_uses_model() -> None:
    plan = DispatchPlan(primary_intent="grinder_conversion", actions=[{"type": "grinder_conversion"}])
    results = _run(plan, gateway=_FakeGateway("C40 #18 大约对应 ZP6 6.0 圈，仅近似。"))
    assert results[0].status == "done"
    assert results[0].source == "model"
    assert "ZP6" in results[0].message


def test_web_verify_degrades_to_local_knowledge() -> None:
    plan = DispatchPlan(primary_intent="web_verify", actions=[{"type": "web_verify"}])
    results = _run(plan)
    assert results[0].type == "web_verify"
    assert results[0].status == "degraded"
    # 明确标注非联网核实。
    assert "非联网" in results[0].message or "联网" in results[0].message


def test_write_capability_is_pending() -> None:
    # 文字建/改豆卡仍是「待确认」动作（不在聊天单轮自动写库），走 pending 引导语。
    plan = DispatchPlan(
        primary_intent="create_or_update_bean_card",
        actions=[{"type": "create_or_update_bean_card"}],
    )
    results = _run(plan)
    assert results[0].status == "pending"
    assert results[0].message


def test_recommend_brew_params_runs_coach_inline() -> None:
    # 「给我出个推荐冲煮方案」改走冲煮教练：聊天里直接出一版方案，而不是 pending 引导去别处。
    plan = DispatchPlan(
        primary_intent="recommend_brew_params",
        actions=[{"type": "recommend_brew_params"}],
    )
    results = _run(
        plan,
        message="按照4.2的研磨度，给我出个推荐冲煮方案",
        gateway=_FakeGateway("苏丹汝魅 V60 方案：粉量15g，水量240g，水温92℃。"),
        active_context={
            "bean": {"name": "苏丹汝魅"},
            "equipment": {"dripper": "V60", "grinder": "ZP6S", "filter_media": "纸滤"},
            "recipe": None,
        },
    )
    assert results[0].type == "recommend_brew_params"
    assert results[0].status == "done"
    assert results[0].source == "model"
    # 方案正文应进主回复（recommend_brew_params 是正文型回答），而非被丢弃落到通用兜底。
    reply = assemble_reply(plan, results)
    assert reply is not None and "水温92℃" in reply


def test_recommend_brew_params_never_hits_generic_fallback_when_degraded() -> None:
    # 模型不可用时教练回本地保守兜底；assemble_reply 仍须给出非空回复，
    # 端点层那句完全通用的「我可以帮你聊咖啡豆…」兜底不应被触发。
    plan = DispatchPlan(
        primary_intent="recommend_brew_params",
        actions=[{"type": "recommend_brew_params"}],
    )
    results = _run(plan, message="给我出个推荐冲煮方案")  # gateway=None → 本地兜底
    assert results[0].status == "done"
    reply = assemble_reply(plan, results)
    assert reply and reply.strip() == LOCAL_COACH_FALLBACK.strip()


def test_pending_guidance_surfaces_as_reply() -> None:
    # pending 引导语（如「到豆仓新建豆卡」）以前被 assemble_reply 漏掉、落到通用兜底；
    # 现在应作为主回复返回，让用户看到对得上的引导。
    plan = DispatchPlan(
        primary_intent="create_or_update_bean_card",
        actions=[{"type": "create_or_update_bean_card"}],
    )
    results = _run(plan, message="帮我新建一张耶加雪菲豆卡")
    reply = assemble_reply(plan, results)
    assert reply is not None and "豆仓" in reply


def test_intent_only_yields_no_result() -> None:
    plan = DispatchPlan(primary_intent="ask_clarification", actions=[{"type": "ask_clarification"}])
    results = _run(plan)
    assert results == []


def test_coach_receives_hydrated_active_entities() -> None:
    # 水合后的 active_context（bean/equipment/recipe）应分别进 coach 的 user 消息，
    # 而不是把整个 session_state 当 active_bean 塞进去。
    captured: dict = {}

    class _CaptureGW:
        enabled = True
        vision_enabled = True

        async def chat(self, **kwargs):  # noqa: ANN003
            captured["user"] = kwargs["messages"][1]["content"]
            return SimpleNamespace(content="教练回复", model="fake")

    plan = DispatchPlan(primary_intent="adjust_brew_params", actions=[{"type": "adjust_brew_params"}])
    active_context = {
        "bean": {"name": "巴拿马 瑰夏"},
        "equipment": {"brew_method": "滤杯冲煮", "dripper": "V60", "grinder": "C40"},
        "recipe": {"dose_g": 15, "water_ml": 240},
    }
    results = _run(plan, gateway=_CaptureGW(), active_context=active_context)
    assert results[0].status == "done"
    assert results[0].source == "model"
    # active 实体出现在喂给教练的 user 消息里。
    assert "巴拿马 瑰夏" in captured["user"]
    assert "V60" in captured["user"]
    assert "240" in captured["user"]


def test_coach_action_receives_original_images() -> None:
    captured: dict = {}

    class _CaptureGW:
        enabled = True
        vision_enabled = True

        async def chat(self, **kwargs):  # noqa: ANN003
            captured["model"] = kwargs["model"]
            captured["user"] = kwargs["messages"][1]["content"]
            return SimpleNamespace(content="教练看图后回复", model="fake")

    plan = DispatchPlan(primary_intent="adjust_brew_params", actions=[{"type": "adjust_brew_params"}])
    results = _run(
        plan,
        attachments=[{"type": "image", "data_url": _IMG}],
        settings=SimpleNamespace(vision_model="kimi-k2.6"),
        gateway=_CaptureGW(),
    )
    assert results[0].status == "done"
    assert captured["model"] == "kimi-k2.6"
    assert isinstance(captured["user"], list)
    assert any(p.get("type") == "image_url" and p["image_url"]["url"] == _IMG for p in captured["user"])


def test_brew_parse_uses_history_for_record_this_brew() -> None:
    plan = DispatchPlan(primary_intent="brew_record_parse", actions=[{"type": "brew_record_parse"}])
    results = _run(
        plan,
        message="帮我记录这次冲煮",
        history=[
            {"role": "user", "content": "今天用 V60 冲巴拿马瑰夏，15g 粉，225ml，93°C，2:40，ZP6S 5.0 圈，纸滤。"},
        ],
    )
    r = results[0]
    assert r.type == "brew_record_parse"
    assert r.status == "done"
    assert r.output["draft"]["device"] == "V60"
    assert r.output["draft"]["grinder"] == "ZP6S"
    assert r.output["draft"]["filter_media"] == "纸滤"
    assert r.output["draft"]["dose_g"] == 15
    assert r.output["draft"]["water_ml"] == 225


def test_equipment_capture_outputs_item_draft() -> None:
    plan = DispatchPlan(primary_intent="equipment_capture", actions=[{"type": "equipment_capture"}])
    results = _run(plan, message="我新买了一个法压壶，也在用 ZP6S")
    r = results[0]
    assert r.type == "equipment_capture"
    assert r.status == "done"
    assert {"category": "brewer", "name": "法压壶"} in r.output["items"]
    assert {"category": "grinder", "name": "ZP6S"} in r.output["items"]


def test_equipment_capture_dedupes_known_items() -> None:
    plan = DispatchPlan(primary_intent="equipment_capture", actions=[{"type": "equipment_capture"}])
    results = _run(
        plan,
        message="我用 ZP6S",
        active_context={"equipment_items": [{"category": "grinder", "name": "ZP6S"}]},
    )
    r = results[0]
    assert r.type == "equipment_capture"
    assert r.output is None
    assert "已经" in r.message


def test_brew_draft_can_append_unsaved_equipment_capture() -> None:
    result = ActionResult(
        type="brew_record_parse",
        status="done",
        source="local",
        output={
            "draft": {"device": "V60", "grinder": "ZP6S", "filter_media": "纸滤"},
            "raw_input": "V60 ZP6S 纸滤 15g 225ml",
        },
    )
    results = [result]
    ensure_equipment_capture_for_brew(results, active_context={"equipment_items": [{"category": "brewer", "name": "V60"}]})
    eq = [r for r in results if r.type == "equipment_capture"]
    assert eq
    assert {"category": "grinder", "name": "ZP6S"} in eq[0].output["items"]
    assert {"category": "filter_media", "name": "纸滤"} in eq[0].output["items"]


def test_knowledge_action_receives_original_images() -> None:
    captured: dict = {}

    class _CaptureGW:
        enabled = True
        vision_enabled = True

        async def chat(self, **kwargs):  # noqa: ANN003
            captured["model"] = kwargs["model"]
            captured["user"] = kwargs["messages"][1]["content"]
            return SimpleNamespace(content="知识问答看图后回复", model="fake")

    plan = DispatchPlan(primary_intent="knowledge_answer", actions=[{"type": "knowledge_answer"}])
    results = _run(
        plan,
        attachments=[{"type": "image", "data_url": _IMG}],
        settings=SimpleNamespace(vision_model="kimi-k2.6"),
        gateway=_CaptureGW(),
    )
    assert results[0].status == "done"
    assert results[0].message == "知识问答看图后回复"
    assert captured["model"] == "kimi-k2.6"
    assert isinstance(captured["user"], list)
    assert any(p.get("type") == "image_url" and p["image_url"]["url"] == _IMG for p in captured["user"])


def test_pending_writeback_actions_give_guidance() -> None:
    # 写库类动作在聊天里仍 pending（不自动落库），但 message 应是明确引导语，而非"后续阶段接入"的桩。
    # recommend_brew_params 不在此列：它已改走冲煮教练，在聊天里直接出方案（见 test_recommend_brew_params_runs_coach_inline）。
    for intent in ("brew_record_parse", "create_or_update_bean_card"):
        plan = DispatchPlan(primary_intent=intent, actions=[{"type": intent}])
        results = _run(plan)
        assert results[0].status == "pending"
        assert results[0].message and "后续阶段接入" not in results[0].message


def test_assemble_reply_uses_direct_reply_for_intent_only() -> None:
    plan = DispatchPlan(primary_intent="ask_clarification", direct_reply="想问豆子还是冲煮？")
    assert assemble_reply(plan, []) == "想问豆子还是冲煮？"


def test_assemble_reply_prefers_executed_primary_result() -> None:
    plan = DispatchPlan(primary_intent="knowledge_answer", direct_reply="我先简单说一下。")
    results = [
        ActionResult(type="knowledge_answer", status="done", message="知识库答案带来源。"),
    ]
    assert assemble_reply(plan, results) == "知识库答案带来源。"


def test_assemble_reply_combines_multiple_answers_primary_first() -> None:
    # 一轮多个实质回答（知识库 + 联网核实各答一部分）合并进主回复，主意图在前，卡片只剩链接。
    plan = DispatchPlan(primary_intent="web_verify")
    results = [
        ActionResult(type="knowledge_answer", status="done", message="普通知识答案。"),
        ActionResult(type="web_verify", status="degraded", message="联网核实降级答案。"),
    ]
    assert assemble_reply(plan, results) == "联网核实降级答案。\n\n普通知识答案。"


def test_assemble_reply_falls_back_to_first_displayable_result() -> None:
    plan = DispatchPlan(primary_intent="web_verify")
    results = [
        ActionResult(type="web_verify", status="failed", message="失败内容不展示为主回复。"),
        ActionResult(type="knowledge_answer", status="done", message="可展示的兜底答案。"),
    ]
    assert assemble_reply(plan, results) == "可展示的兜底答案。"


def test_assemble_reply_returns_none_when_nothing_displayable() -> None:
    # 真·无可用回复（既无可展示正文、也无 pending 引导、也无 direct_reply）才返回 None；
    # 仅有 failed 结果时不应硬凑出回复。
    plan = DispatchPlan(primary_intent="knowledge_answer")
    results = [
        ActionResult(type="knowledge_answer", status="failed", message="失败内容不展示为主回复。"),
    ]
    assert assemble_reply(plan, results) is None


def test_assemble_reply_surfaces_pending_guidance() -> None:
    # pending 引导语此前被 assemble_reply 漏掉、落到端点层通用兜底；现在应作为主回复返回。
    plan = DispatchPlan(primary_intent="create_or_update_bean_card")
    results = [
        ActionResult(type="create_or_update_bean_card", status="pending", message="到「豆仓」新建 / 编辑。"),
    ]
    assert assemble_reply(plan, results) == "到「豆仓」新建 / 编辑。"


def test_assemble_reply_coach_fallback_does_not_override_real_answer() -> None:
    # 调度器误把问答型请求又附带了教练动作、教练无话可说只回兜底空话；
    # 主回复应是联网核实的真答案，而不是那句模板空话（修复第 2 条）。
    from app.services.brew_coach import LOCAL_COACH_FALLBACK

    plan = DispatchPlan(primary_intent="adjust_brew_params")
    results = [
        ActionResult(type="adjust_brew_params", status="done", message=LOCAL_COACH_FALLBACK),
        ActionResult(type="web_verify", status="done", message="幻刺Pro 手冲约 7–12，意式约 2–4。"),
    ]
    assert assemble_reply(plan, results) == "幻刺Pro 手冲约 7–12，意式约 2–4。"


def test_assemble_reply_keeps_coach_fallback_when_it_is_the_only_answer() -> None:
    # 用户确实只问了教练类问题、又没给上下文，兜底空话就是该展示的回复，不能被丢成空。
    from app.services.brew_coach import LOCAL_COACH_FALLBACK

    plan = DispatchPlan(primary_intent="adjust_brew_params")
    results = [
        ActionResult(type="adjust_brew_params", status="done", message=LOCAL_COACH_FALLBACK),
    ]
    assert assemble_reply(plan, results) == LOCAL_COACH_FALLBACK


# ── 聊天记录冲煮：带参数真解析、纯意图回引导 ──

def test_brew_record_parse_with_params_returns_draft_and_missing() -> None:
    plan = DispatchPlan(primary_intent="brew_record_parse", actions=[{"type": "brew_record_parse"}])
    results = _run(plan, message="帮我记录这次冲煮：15g 粉，270ml 水，96°C，2:30")
    r = results[0]
    assert r.type == "brew_record_parse"
    assert r.status == "done"
    assert r.output["draft"]["dose_g"] == 15
    assert r.output["draft"]["water_ml"] == 270
    assert "missing_fields" in r.output and "device" in r.output["missing_fields"]
    assert "解析出" in r.message and "还缺" in r.message


def test_brew_record_parse_without_params_keeps_guidance() -> None:
    plan = DispatchPlan(primary_intent="brew_record_parse", actions=[{"type": "brew_record_parse"}])
    results = _run(plan, message="我想记录今天的冲煮")
    r = results[0]
    assert r.status == "pending"
    assert "把冲煮参数发我" in r.message
    assert r.output is None


# ── 端点兜底 ensure_brew_draft_result：按「冲煮记录必要字段」判定，刻度换算问句不附草稿 ──

def _ensure_draft(message: str, **overrides) -> list[ActionResult]:
    results: list[ActionResult] = overrides.pop("results", [])
    asyncio.run(
        ensure_brew_draft_result(results, message=message, model="m", gateway=None, **overrides)
    )
    return results


def test_grinder_conversion_question_does_not_attach_brew_draft() -> None:
    # 纯刻度换算问句：含磨豆机名 + 数字 + 「刻度」，但不是一条冲煮记录，不应附草稿卡。
    results = _ensure_draft("C40刻度的22，对应ZP6s是多少")
    assert results == []


def test_full_brew_details_attach_brew_draft() -> None:
    # 真报了冲煮详情（粉/水/温/时多项核心字段）→ 主动给草稿卡。
    results = _ensure_draft("今天 V60，15g 粉，225ml 水，93°C，2:40")
    brew = [r for r in results if r.type == "brew_record_parse"]
    assert brew and isinstance(brew[0].output, dict) and brew[0].output.get("draft")


def test_explicit_record_intent_attaches_even_when_sparse() -> None:
    # 明确说「记录」即便信息少也给草稿卡，引导补全。
    results = _ensure_draft("帮我记录这次冲煮")
    assert any(r.type == "brew_record_parse" for r in results)


def test_mentions_brew_quantity_excludes_grind_scale() -> None:
    assert not _mentions_brew_quantity("C40刻度的22，对应ZP6s是多少")
    assert not _mentions_brew_quantity("ZP6s 用几号刻度合适")
    assert _mentions_brew_quantity("15g 粉，225ml 水，93°C")
    assert _mentions_brew_quantity("粉水比 1:15")
    assert _mentions_brew_quantity("水温 92度")


def test_draft_substance_count_ignores_equipment_only() -> None:
    assert _draft_substance_count({"grinder": "ZP6S", "grind_setting": "22"}) == 0
    assert _draft_substance_count({"dose_g": 15, "water_ml": 225}) == 2
    assert _draft_substance_count({"ratio": "1:15", "brew_steps": [{"time_seconds": 0, "action": "注水"}]}) == 2


# ── 记录豆卡不算冲煮意图 + 追问体系确认轮（关联活跃豆 + 按豆袋官方配方预填）──

def test_record_bean_card_phrasing_is_not_brew_intent() -> None:
    # 「帮我记录这个豆卡 / 这支豆」是录豆卡，不是记冲煮。
    assert _contains_brew_record_hint("帮我记录这个豆卡") is False
    assert _contains_brew_record_hint("帮我记录这支豆") is False
    # 含明确冲煮词仍算冲煮意图。
    assert _contains_brew_record_hint("记录一次冲煮") is True
    assert _contains_brew_record_hint("帮我记录这包豆的冲煮") is True


def test_record_bean_card_does_not_attach_brew_draft() -> None:
    # 「帮我记录这个豆卡」既不该当冲煮意图，也没冲煮量 → 不附冲煮草稿。
    assert _ensure_draft("帮我记录这个豆卡") == []


def test_official_recipe_extracted_from_bean_notes() -> None:
    assert _official_recipe_from_bean({"private_notes": "官方建议：V60 15g 270ml 96℃"}) == "V60 15g 270ml 96℃"
    assert _official_recipe_from_bean({"private_notes": "普通备注"}) is None
    assert _official_recipe_from_bean(None) is None


def test_brew_offer_confirm_links_active_bean_and_prefills_from_bag() -> None:
    # 追问确认轮：明确记录 + 活跃豆有豆袋官方配方 → 草稿关联豆名并预填粉/水/温。
    bean = {"name": "圣洁庄园 苏丹汝魅", "private_notes": "官方建议：V60 15g 270ml 96℃"}
    results = _ensure_draft("记录一次冲煮", active_bean=bean)
    brew = [r for r in results if r.type == "brew_record_parse" and isinstance(r.output, dict)]
    assert brew, results
    draft = brew[0].output["draft"]
    assert draft.get("bean_name") == "圣洁庄园 苏丹汝魅"
    assert draft.get("dose_g") == 15
    assert draft.get("water_ml") == 270
    assert draft.get("water_temp_c") == 96


def test_brew_offer_confirm_blank_without_bag_recipe() -> None:
    # 活跃豆但无官方配方：仍出草稿、关联豆名，量留空待用户填。
    bean = {"name": "测试豆", "private_notes": None}
    results = _ensure_draft("记录一次冲煮", active_bean=bean)
    brew = [r for r in results if r.type == "brew_record_parse" and isinstance(r.output, dict)]
    assert brew
    draft = brew[0].output["draft"]
    assert draft.get("bean_name") == "测试豆"
    assert draft.get("dose_g") is None and draft.get("water_ml") is None
