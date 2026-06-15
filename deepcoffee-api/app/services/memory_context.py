"""统一记忆注入层：把分层记忆汇总成可注入模型的形态。

三层记忆都经这里组装、由端点一次性取出、分发给调度器与各能力：
- L1 工作记忆：最近若干轮对话。history_messages 给自由文本能力当多轮消息；
  history_text 给 JSON 调度器（避免历史里的自然语言把调度器带偏出 JSON）。
- L2 情景摘要：summary_text（阶段 2 填充）。
- L3 用户画像：profile_text（阶段 3 填充）。
- L4 实体记忆：仍走端点现有 active_context / recent_beans 等，不在此重复。

构造保持纯函数、不调模型、不抛业务异常：记忆缺失只是少点上下文，绝不打断对话。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 注入给模型的最近轮数（不含本轮）。够接住多轮上下文，又不让输入无限膨胀。
DEFAULT_HISTORY_TURNS = 10
# 历史里的图片不重复走 vision（成本高）：用占位文本表示「这轮带过图」。
_IMAGE_PLACEHOLDER = "[图片]"


@dataclass
class MemoryContext:
    """一轮对话要注入模型的全部记忆，已按用途整理好。"""

    history_messages: list[dict[str, str]] = field(default_factory=list)  # L1：多轮消息
    history_text: str = ""  # L1：紧凑文本（给 JSON 调度器）
    summary_text: str = ""  # L2：主题式长期摘要（阶段 2）
    profile_text: str = ""  # L3：用户画像摘要（阶段 3）


def _turn_to_text(turn: dict[str, Any]) -> str:
    """一轮消息 → 注入用文本；图片以占位表示，不带 base64 / URL。"""
    content = (turn.get("content") or "").strip()
    images = turn.get("images") or []
    if images:
        placeholder = " ".join([_IMAGE_PLACEHOLDER] * len(images))
        content = f"{content} {placeholder}".strip()
    return content


def build_history(
    recent_messages: list[dict[str, Any]] | None,
    *,
    max_turns: int = DEFAULT_HISTORY_TURNS,
) -> tuple[list[dict[str, str]], str]:
    """从已存的历史轮次构造 (history_messages, history_text)。

    端点在 append 本轮消息之前调用，故 recent_messages 不含本轮，无需排除当前轮。
    只保留 user / assistant 文本轮；空轮跳过。
    """
    turns = [t for t in (recent_messages or []) if isinstance(t, dict)]
    messages: list[dict[str, str]] = []
    for t in turns[-max_turns:]:
        role = t.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _turn_to_text(t)
        if not text:
            continue
        messages.append({"role": role, "content": text})
    lines = [f"{'用户' if m['role'] == 'user' else '助手'}：{m['content']}" for m in messages]
    return messages, "\n".join(lines)


_KIND_LABELS = {
    "taste": "口味",
    "equipment": "器具",
    "habit": "习惯",
    "goal": "目标",
    "fact": "其他",
}


def _memory_field(m: Any, name: str) -> Any:
    """记忆条目兼容 ORM 对象与 dict 两种形态取字段。"""
    return m.get(name) if isinstance(m, dict) else getattr(m, name, None)


def build_profile_text(user_memories: list[Any] | None) -> str:
    """把 active 记忆按 kind 归类成一段画像摘要文本（L3）。"""
    if not user_memories:
        return ""
    by_kind: dict[str, list[str]] = {}
    for m in user_memories:
        content = _memory_field(m, "content")
        if not content:
            continue
        kind = _memory_field(m, "kind") or "fact"
        by_kind.setdefault(kind, []).append(str(content))
    lines = [
        f"{_KIND_LABELS.get(kind, kind)}：{'；'.join(items)}"
        for kind, items in by_kind.items()
    ]
    return "\n".join(lines)


def build_summary_text(summary: list[Any] | None) -> str:
    """把会话摘要（list[{topic, content, time_hint}]）拼成可注入文本（L2）。"""
    if not summary:
        return ""
    lines: list[str] = []
    for it in summary:
        if not isinstance(it, dict):
            continue
        content = (it.get("content") or "").strip()
        if not content:
            continue
        topic = (it.get("topic") or "").strip()
        hint = (it.get("time_hint") or "").strip()
        line = f"- {topic}：{content}" if topic else f"- {content}"
        if hint:
            line += f"（{hint}）"
        lines.append(line)
    return "\n".join(lines)


def build_memory_context(
    cs: Any,
    *,
    user_memories: list[Any] | None = None,
    max_turns: int = DEFAULT_HISTORY_TURNS,
) -> MemoryContext:
    """组装本轮记忆注入上下文。

    - L1：最近对话（history_messages / history_text）。
    - L2：会话摘要（summary_text）。
    - L3：用户画像（profile_text）。
    L2+L3 合并成一条背景 system 消息置于 history_messages 最前，让自由文本能力随 *history 一起看到
    （无需各自再加参数）。
    """
    dialog_messages, history_text = build_history(
        getattr(cs, "recent_messages", None), max_turns=max_turns
    )
    profile_text = build_profile_text(user_memories)
    summary_text = build_summary_text(getattr(cs, "summary", None))
    history_messages: list[dict[str, str]] = list(dialog_messages)
    parts: list[str] = []
    if profile_text:
        parts.append(f"用户长期偏好与习惯：\n{profile_text}")
    if summary_text:
        parts.append(f"更早对话摘要：\n{summary_text}")
    if parts:
        background = "（以下为背景参考，不要照搬复述给用户）\n" + "\n\n".join(parts)
        history_messages.insert(0, {"role": "system", "content": background})
    return MemoryContext(
        history_messages=history_messages,
        history_text=history_text,
        summary_text=summary_text,
        profile_text=profile_text,
    )
