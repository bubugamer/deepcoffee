"""会话滚动摘要（L2）：把被移出窗口的较早对话，增量并入主题式长期摘要。

设计同全局约定：有模型用模型、没有就不更新（返回 None，调用方保留旧摘要）。
摘要按主题归类、带时间线索；绝不抛业务异常打断对话。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.prompts import SESSION_SUMMARY_SYSTEM, SESSION_SUMMARY_USER_TEMPLATE
from app.services.model_gateway import ModelGateway, model_gateway
from app.services.model_json import ModelJSONError, chat_json

logger = logging.getLogger(__name__)


def _dialog_text(turns: list[dict[str, Any]] | None) -> str:
    """把若干轮消息转成「用户/助手：内容」文本；图片以占位表示。"""
    lines: list[str] = []
    for t in turns or []:
        if not isinstance(t, dict):
            continue
        role = t.get("role")
        who = "用户" if role == "user" else "助手" if role == "assistant" else None
        if who is None:
            continue
        content = (t.get("content") or "").strip()
        if t.get("images"):
            content = f"{content} [图片]".strip()
        if content:
            lines.append(f"{who}：{content}")
    return "\n".join(lines)


def _as_text(value: Any) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return "（无）"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


async def update_summary(
    *,
    existing_summary: list[dict[str, Any]] | None,
    dropped_turns: list[dict[str, Any]] | None,
    model: str,
    gateway: ModelGateway | None = None,
) -> list[dict[str, Any]] | None:
    """把 dropped_turns 增量并入 existing_summary，返回新摘要数组。

    网关不可用 / 无被裁对话 / 调用失败 / 输出不合规时返回 None（调用方保留旧摘要、不更新）。
    """
    gw = gateway or model_gateway
    dialog = _dialog_text(dropped_turns)
    if not gw.enabled or not dialog:
        return None
    user_content = SESSION_SUMMARY_USER_TEMPLATE.format(
        existing_summary=_as_text(existing_summary),
        dropped_dialog=dialog,
    )
    messages = [
        {"role": "system", "content": SESSION_SUMMARY_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    try:
        data = await chat_json(
            gw,
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=900,
            required_keys=["summary"],
            allowed_keys=["summary"],
        )
    except ModelJSONError as exc:
        logger.warning("session_summary JSON invalid, keep old summary: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 — 摘要失败不影响对话
        logger.warning("session_summary model call failed, keep old summary: %s", exc)
        return None

    items = data.get("summary")
    if not isinstance(items, list):
        return None
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        topic = it.get("topic")
        content = it.get("content")
        topic = topic.strip() if isinstance(topic, str) else ""
        content = content.strip() if isinstance(content, str) else ""
        if not topic or not content:
            continue
        time_hint = it.get("time_hint")
        time_hint = time_hint.strip() if isinstance(time_hint, str) else ""
        out.append({"topic": topic, "content": content, "time_hint": time_hint})
    return out or None
