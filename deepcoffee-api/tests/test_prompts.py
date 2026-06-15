"""提示词集中地与文档的「逐字一致」回归测试。

app/prompts 是代码侧 source-of-truth，必须与 docs/deepcoffee-ai-prompts.md 逐字一致。
这里把每个提示词常量当作子串在文档里查，任一漂移即失败，防止「改了文档没改代码 / 改了
代码没改文档」。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import prompts

# tests/ -> deepcoffee-api/ -> repo root；文档在 repo_root/docs。
_DOC_PATH = Path(__file__).resolve().parents[2] / "docs" / "deepcoffee-ai-prompts.md"


@pytest.fixture(scope="module")
def doc_text() -> str:
    return _DOC_PATH.read_text(encoding="utf-8")


# 这些常量必须逐字出现在文档对应的代码块里。
_VERBATIM_CONSTANTS = [
    "COFFEA_DISPATCH_SYSTEM",
    "COFFEA_DISPATCH_USER_TEMPLATE",
    "IMAGE_UNDERSTANDING_SYSTEM",
    "IMAGE_UNDERSTANDING_USER_TEMPLATE",
    "KNOWLEDGE_ANSWER_SYSTEM",
    "BEAN_PARSE_SYSTEM",
    "BEAN_DRAFT_INTRO",
    "BEAN_SAVED_SUCCESS_TEMPLATE",
    "BEAN_RECOMMEND_SYSTEM",
    "BEAN_RECOMMEND_USER_TEMPLATE",
    "BREW_PARSE_SYSTEM",
    "BREW_RECAP_SYSTEM",
    "BREW_RECAP_USER_TEMPLATE",
    "BREW_COACH_SYSTEM",
    "BREW_COACH_USER_TEMPLATE",
    "WEB_VERIFY_SYSTEM",
    "WEB_VERIFY_USER_TEMPLATE",
    "MEMORY_EXTRACT_SYSTEM",
    "MEMORY_EXTRACT_USER_TEMPLATE",
    "SESSION_SUMMARY_SYSTEM",
    "SESSION_SUMMARY_USER_TEMPLATE",
]


@pytest.mark.parametrize("name", _VERBATIM_CONSTANTS)
def test_prompt_matches_doc_verbatim(name: str, doc_text: str) -> None:
    value = getattr(prompts, name)
    assert value, f"{name} is empty"
    assert value in doc_text, f"{name} drifted from docs/deepcoffee-ai-prompts.md"


def test_doc_exists() -> None:
    assert _DOC_PATH.exists(), f"prompts doc missing at {_DOC_PATH}"


def test_ai_answer_uses_centralized_prompt() -> None:
    # 已上线的知识库问答必须复用集中后的提示词，行为不变。
    from app.services.ai_answer import _SYSTEM_PROMPT

    assert _SYSTEM_PROMPT == prompts.KNOWLEDGE_ANSWER_SYSTEM


def test_raw_text_user_templates_are_passthrough() -> None:
    # 文档里这两处 user 模板是「直接传原文」，代码用 {text} 占位，刻意与文档措辞不同。
    assert prompts.BEAN_PARSE_USER_TEMPLATE == "{text}"
    assert prompts.BREW_PARSE_USER_TEMPLATE == "{text}"


# 直接产出「用户可见自由文本回复」的提示词，禁止出现内部能力代号 / 字段名，
# 防止模型把工具名（如 web_verify）照搬进给用户的回复。
# 注：COFFEA_DISPATCH_SYSTEM / IMAGE_UNDERSTANDING_SYSTEM / 各 *_PARSE_SYSTEM 是结构化 JSON
# 能力，功能上必须把这些代号当枚举值列出、不直接展示给终端用户，故刻意不纳入此断言。
_USER_FACING_FREEFORM = [
    "KNOWLEDGE_ANSWER_SYSTEM",
    "BREW_COACH_SYSTEM",
    "WEB_VERIFY_SYSTEM",
    "BEAN_RECOMMEND_SYSTEM",
]

_INTERNAL_CODENAMES = [
    "web_verify",
    "knowledge_answer",
    "read_bean_card_image",
    "assess_brew_photo",
    "create_or_update_bean_card",
    "recommend_brew_params",
    "adjust_brew_params",
    "scale_recipe",
    "grinder_conversion",
    "brew_record_parse",
    "equipment_advice",
    "storage_resting_advice",
    "ask_clarification",
    "out_of_scope",
    "direct_answer",
    "primary_intent",
]


@pytest.mark.parametrize("name", _USER_FACING_FREEFORM)
def test_user_facing_prompts_have_no_internal_codenames(name: str) -> None:
    value = getattr(prompts, name)
    leaked = [token for token in _INTERNAL_CODENAMES if token in value]
    assert not leaked, f"{name} 暴露了内部代号: {leaked}"
