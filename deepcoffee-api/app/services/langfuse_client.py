"""Langfuse trace 适配器（AI 观测，Phase 3）。

设计原则，和 new-api / billing 一致：**未配置即 no-op，优雅降级**。
- 没配 langfuse_public_key / secret_key / host → `enabled=False`，所有 trace 调用是空操作。
- 装没装 `langfuse` SDK 都不影响业务：SDK 缺失也只是 no-op + 一次告警。
- 观测永远不能让业务失败：所有上报都包在 try/except 里，异常只记日志。

脱敏：`DEEPCOFFEE_LOG_FULL_AI_IO=true` 时才完整记录用户输入/模型输出，否则只记长度与
摘要（`{"chars": N, "redacted": true}`）。内部 token、支付字段、完整隐私字段一律不上报。

记录的 trace 名对齐计划：`brew_parse`、`brew_recap`、`bean_parse`、`bean_recommend_params`、
`knowledge_file_select`、`knowledge_answer` 等。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# 永远不上报的敏感键（即便 log_full_ai_io=true 也脱敏）。
_SENSITIVE_KEYS = {
    "internal_token",
    "token",
    "password",
    "secret",
    "secret_key",
    "authorization",
    "api_key",
    "access_token",
}


class LangfuseTracer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: Any | None = None
        self._init_failed = False

    @property
    def enabled(self) -> bool:
        s = self.settings
        return bool(s.langfuse_public_key and s.langfuse_secret_key and s.langfuse_host)

    def _get_client(self) -> Any | None:
        if not self.enabled or self._init_failed:
            return None
        if self._client is not None:
            return self._client
        try:
            from langfuse import Langfuse  # 可选依赖；未装即降级

            self._client = Langfuse(
                public_key=self.settings.langfuse_public_key,
                secret_key=self.settings.langfuse_secret_key,
                host=self.settings.langfuse_host,
            )
        except Exception as exc:  # noqa: BLE001 — SDK 缺失/版本不符都降级
            self._init_failed = True
            logger.warning("Langfuse configured but client init failed (tracing disabled): %s", exc)
            return None
        return self._client

    # ---- 脱敏 ----
    def _mask_value(self, value: Any) -> Any:
        if not self.settings.log_full_ai_io and isinstance(value, str):
            return {"chars": len(value), "redacted": True}
        return value

    def _mask_metadata(self, metadata: dict[str, Any] | None) -> dict[str, Any] | None:
        if not metadata:
            return metadata
        cleaned: dict[str, Any] = {}
        for key, val in metadata.items():
            if key.lower() in _SENSITIVE_KEYS:
                cleaned[key] = {"redacted": True}
            else:
                cleaned[key] = val
        return cleaned

    def trace(
        self,
        name: str,
        *,
        trace_id: str,
        user_id: str | None = None,
        input: Any = None,
        output: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """上报一次 AI 调用 trace。未配置/出错都是 no-op，绝不抛异常打断业务。"""
        client = self._get_client()
        if client is None:
            return
        try:
            client.trace(
                id=trace_id,
                name=name,
                user_id=user_id,
                input=self._mask_value(input),
                output=self._mask_value(output),
                metadata=self._mask_metadata(metadata),
            )
        except Exception as exc:  # noqa: BLE001 — 观测失败不影响业务
            logger.warning("Langfuse trace '%s' failed: %s", name, exc)


langfuse_tracer = LangfuseTracer()
