"""结构化（JSON）模型调用的小工具：调用 → 解析 → 校验，失败即抛错。

对应提示词清单（`docs/deepcoffee-ai-prompts.md`）实现计划第 1 步「基建」里的
「一个『调用并解析 JSON、失败抛错』的小工具（带白名单/范围校验）」。

设计与全局约定一致——**有模型用模型、没有就回退本地**：本模块只负责「把模型那条
结构化结果安全地拿到、解析、校验」，任何不合规都抛 ``ModelJSONError``；**是否回退本地
由调用方 try/except 决定**，本模块不吞错也不兜底，保证降级路径清晰可测。

这里全部是纯函数 + 一个薄封装 ``chat_json``，不依赖具体能力，便于单测。
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # 仅类型提示，避免与 model_gateway 形成运行时循环依赖。
    from app.services.model_gateway import ModelGateway

# 抽取/结构化类能力统一用这个 response_format（见清单 §0 默认入参）。
JSON_RESPONSE_FORMAT: dict[str, str] = {"type": "json_object"}

_CODE_FENCE_RE = re.compile(r"^```[a-zA-Z0-9]*\s*|\s*```$")


class ModelJSONError(ValueError):
    """模型结构化输出不合规（空、非 JSON、缺键、含非白名单键、越界）。

    调用方应捕获它并回退本地启发式，绝不把它当成功结果。
    """


def extract_json_object(content: str | None) -> dict[str, Any]:
    """把模型返回的文本解析成一个 JSON 对象。

    宽容地剥掉 ```json 代码块围栏和首尾噪声；解析失败 / 不是对象 → ``ModelJSONError``。
    （提示词里已要求只吐 JSON，这里只是对偶发的围栏/前后缀做防御。）
    """
    if not content or not content.strip():
        raise ModelJSONError("model returned empty content")
    text = content.strip()
    # 去掉整体的 ```json ... ``` 围栏（如果模型没听话加了）。
    if text.startswith("```"):
        text = _CODE_FENCE_RE.sub("", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 退一步：截取第一个 { 到最后一个 } 再试一次，兜住前后多余文字。
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ModelJSONError(f"model output is not valid JSON: {text[:120]!r}") from None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            raise ModelJSONError(f"model output is not valid JSON: {text[:120]!r}") from None
    if not isinstance(data, dict):
        raise ModelJSONError(f"model output is not a JSON object: {type(data).__name__}")
    return data


def require_keys(data: dict[str, Any], keys: list[str]) -> None:
    """缺少任一必填键 → ``ModelJSONError``。"""
    missing = [k for k in keys if k not in data]
    if missing:
        raise ModelJSONError(f"model JSON missing required keys: {missing}")


def whitelist_keys(data: dict[str, Any], allowed: list[str], *, strict: bool = False) -> dict[str, Any]:
    """只保留白名单内的键。

    ``strict=True`` 时，出现白名单外的键直接抛错（用于「不要新增任何键」的强约束能力）；
    默认宽松，丢弃多余键即可。
    """
    extra = [k for k in data if k not in allowed]
    if extra and strict:
        raise ModelJSONError(f"model JSON has unexpected keys: {extra}")
    return {k: v for k, v in data.items() if k in allowed}


def check_number_in_range(
    value: Any, *, field: str, low: float, high: float, allow_none: bool = False
) -> float | None:
    """数值范围校验（如水温 85–96）。越界 / 非数字 → ``ModelJSONError``。"""
    if value is None:
        if allow_none:
            return None
        raise ModelJSONError(f"field {field!r} is required but null")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelJSONError(f"field {field!r} is not a number: {value!r}")
    if not (low <= value <= high):
        raise ModelJSONError(f"field {field!r}={value} out of range [{low}, {high}]")
    return float(value)


async def chat_json(
    gateway: "ModelGateway",
    *,
    user_token: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.0,
    max_tokens: int | None = None,
    allowed_keys: list[str] | None = None,
    required_keys: list[str] | None = None,
    strict_keys: bool = False,
    extra_body: dict | None = None,
) -> dict[str, Any]:
    """调用 JSON 模式、解析并按需做键校验，失败抛 ``ModelJSONError``。

    薄封装：固定 ``response_format={"type": "json_object"}``。网关层异常（未配网关、
    模型报错）按原样向上抛；本函数只在「内容拿到但不合规」时抛 ``ModelJSONError``。
    调用方统一 try/except 后回退本地。
    """
    result = await gateway.chat(
        user_token=user_token,
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=JSON_RESPONSE_FORMAT,
        extra_body=extra_body,
    )
    data = extract_json_object(result.content)
    if required_keys:
        require_keys(data, required_keys)
    if allowed_keys is not None:
        data = whitelist_keys(data, allowed_keys, strict=strict_keys)
    return data
