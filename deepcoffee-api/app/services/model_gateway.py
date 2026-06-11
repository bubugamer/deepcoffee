"""Model gateway: 所有模型请求由 deepcoffee-api 发起，经 new-api 的 OpenAI 兼容接口调用，
用对应用户的内部 token，用量自动计入该用户的 new-api 影子账户。

未配置 new-api 时不可用（调用方应回退到本地规则）。Phase 4 接入复盘/解析/问答时使用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError


@dataclass
class ChatResult:
    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def is_insufficient_quota(exc: BaseException) -> bool:
    """识别 new-api 的「影子账户余额耗尽」错误（insufficient_user_quota / 预扣费失败）。

    各 AI 链路在降级到本地兜底时用它区分「余额烧光」与普通故障——前者必须显式
    告知用户去找管理员充值，否则 AI 只是静默变笨，没人知道为什么。
    """
    message = str(exc)
    return "insufficient_user_quota" in message or "预扣费额度失败" in message


class ModelGateway:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.new_api_base_url)

    async def chat(
        self,
        *,
        user_token: str,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_format: dict | None = None,
        extra_body: dict | None = None,
    ) -> ChatResult:
        # messages 直接透传：content 既可是纯字符串，也可是 OpenAI 多模态分块数组
        # （[{"type":"text",...}, {"type":"image_url","image_url":{"url":"data:image/...;base64,..."}}]），
        # 让 vision 模型（如 kimi-k2.6）能收图片。见 docs/deepcoffee-ai-prompts.md §2。
        if not self.enabled:
            raise AppError(503, "model_gateway_disabled", "Model gateway (new-api) is not configured.")
        base = self.settings.new_api_base_url.rstrip("/")
        payload: dict = {"model": model, "messages": messages, "temperature": temperature}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        # 抽取/结构化类能力传 {"type": "json_object"}，让模型只吐 JSON（见 prompts 清单 §0 默认入参）。
        if response_format is not None:
            payload["response_format"] = response_format
        # 透传厂商专有参数（如 Moonshot 关思考 {"thinking": {"type": "disabled"}}）。
        if extra_body:
            payload.update(extra_body)
        async with httpx.AsyncClient(base_url=base, timeout=60) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"},
            )
            if resp.status_code >= 400:
                raise AppError(502, "model_call_failed", f"new-api model call failed: {resp.text[:300]}")
            data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content", "")
        usage = data.get("usage") or {}
        return ChatResult(
            content=content,
            model=data.get("model", model),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )


model_gateway = ModelGateway()
