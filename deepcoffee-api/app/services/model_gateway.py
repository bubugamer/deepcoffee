"""Model gateway: DeepCoffee backend calls an OpenAI-compatible provider directly.

User quota is enforced inside DeepCoffee before requests reach this gateway. The
provider key is server-side only; callers never pass per-user model tokens.
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


def is_provider_quota_error(exc: BaseException) -> bool:
    """Best-effort classification for provider-side key quota/balance failures.

    覆盖 DeepSeek（402 "Insufficient Balance"）、Moonshot（exceeded_current_quota /
    insufficient balance）及通用 OpenAI 兼容网关的 insufficient_*_quota / rate_limit 文案。
    这是**服务端 key 的问题**（管理员需充值），不是单个用户的额度。
    """
    lowered = str(exc).lower()
    return (
        ("insufficient" in lowered and ("quota" in lowered or "balance" in lowered))
        or "exceeded_current_quota" in lowered
        or "rate_limit" in lowered
    )


class ModelGateway:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return self.settings.model_gateway_enabled

    @property
    def vision_enabled(self) -> bool:
        return self.settings.vision_gateway_enabled

    def _endpoint_for_model(self, model: str) -> tuple[str, str]:
        if self.settings.vision_model and model == self.settings.vision_model:
            if not self.vision_enabled:
                raise AppError(503, "vision_gateway_disabled", "Vision model gateway is not configured.")
            return self.settings.vision_model_base_url.rstrip("/"), self.settings.vision_model_api_key
        if not self.enabled:
            raise AppError(503, "model_gateway_disabled", "Model gateway is not configured.")
        return self.settings.model_base_url.rstrip("/"), self.settings.model_api_key

    async def chat(
        self,
        *,
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
        base, api_key = self._endpoint_for_model(model)
        is_vision = bool(self.settings.vision_model and model == self.settings.vision_model)
        # 思考类模型（deepseek-v4-pro / kimi-k2.6）默认开思考：慢到几十秒（超前端等待）、把 max_tokens
        # 吃光导致正文为空、且对 temperature 有古怪限制（开思考只认 1、关思考又只认某值）。开此配置后
        # 下发 {"thinking":{"type":"disabled"}} 关掉思考、并**省略 temperature** 用模型默认，
        # 实测变 1~3 秒、正文完整、不再被 temperature 报错打回。
        disable_thinking = (
            self.settings.vision_model_disable_thinking if is_vision else self.settings.model_disable_thinking
        )
        payload: dict = {"model": model, "messages": messages}
        if not disable_thinking:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        # 抽取/结构化类能力传 {"type": "json_object"}，让模型只吐 JSON（见 prompts 清单 §0 默认入参）。
        if response_format is not None:
            payload["response_format"] = response_format
        effective_extra: dict = dict(extra_body or {})
        if disable_thinking:
            effective_extra.setdefault("thinking", {"type": "disabled"})
        if effective_extra:
            payload.update(effective_extra)
        # 视觉模型（kimi-k2.6）较慢，单张图可达数十秒、两张图更久；放宽到 120s 避免调用被中途掐断回退。
        async with httpx.AsyncClient(base_url=base, timeout=120) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            if resp.status_code >= 400:
                raise AppError(502, "model_call_failed", f"model provider call failed: {resp.text[:300]}")
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
