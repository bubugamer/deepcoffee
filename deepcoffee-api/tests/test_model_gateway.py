from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.services import model_gateway as model_gateway_module
from app.services.model_gateway import ModelGateway


class _FakeResponse:
    status_code = 200
    text = "{}"

    def json(self) -> dict:
        return {
            "model": "provider-model",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        }


class _FakeClient:
    calls: list[dict] = []

    def __init__(self, *, base_url: str, timeout: int) -> None:
        self.base_url = base_url
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):  # noqa: ANN002
        return False

    async def post(self, path: str, *, json: dict, headers: dict) -> _FakeResponse:  # noqa: A002
        self.calls.append({"base_url": self.base_url, "path": path, "json": json, "headers": headers})
        return _FakeResponse()


def _settings(**overrides):
    data = {
        "model_gateway_enabled": True,
        "vision_gateway_enabled": False,
        "model_base_url": "https://models.example/v1",
        "model_api_key": "server-model-key",
        "vision_model_base_url": None,
        "vision_model_api_key": None,
        "vision_model": "vision-model",
        "model_disable_thinking": False,
        "vision_model_disable_thinking": False,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_chat_uses_server_side_model_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClient.calls = []
    monkeypatch.setattr(model_gateway_module.httpx, "AsyncClient", _FakeClient)
    gateway = ModelGateway(_settings())

    result = asyncio.run(
        gateway.chat(model="text-model", messages=[{"role": "user", "content": "hi"}], temperature=0)
    )

    assert result.content == "ok"
    assert _FakeClient.calls[0]["base_url"] == "https://models.example/v1"
    assert _FakeClient.calls[0]["headers"]["Authorization"] == "Bearer server-model-key"
    # 默认（未关思考）：照常传 temperature、不带 thinking 参数
    assert _FakeClient.calls[0]["json"]["temperature"] == 0
    assert "thinking" not in _FakeClient.calls[0]["json"]


def test_chat_injects_current_date_into_system(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    _FakeClient.calls = []
    monkeypatch.setattr(model_gateway_module.httpx, "AsyncClient", _FakeClient)
    gateway = ModelGateway(_settings())

    asyncio.run(
        gateway.chat(
            model="text-model",
            messages=[{"role": "system", "content": "你是助手"}, {"role": "user", "content": "hi"}],
        )
    )

    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    sys_msg = _FakeClient.calls[0]["json"]["messages"][0]
    assert sys_msg["role"] == "system"
    assert "你是助手" in sys_msg["content"]  # 原 system 仍在
    assert "当前日期" in sys_msg["content"] and today in sys_msg["content"]  # 注入了今天


def test_chat_disable_thinking_omits_temperature_and_sends_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClient.calls = []
    monkeypatch.setattr(model_gateway_module.httpx, "AsyncClient", _FakeClient)
    gateway = ModelGateway(_settings(model_disable_thinking=True))

    asyncio.run(
        gateway.chat(model="text-model", messages=[{"role": "user", "content": "hi"}], temperature=0.3)
    )

    payload = _FakeClient.calls[0]["json"]
    assert "temperature" not in payload  # 关思考时省略 temperature，用模型默认
    assert payload["thinking"] == {"type": "disabled"}


def test_vision_model_requires_vision_gateway() -> None:
    gateway = ModelGateway(_settings())

    with pytest.raises(AppError) as exc:
        asyncio.run(gateway.chat(model="vision-model", messages=[{"role": "user", "content": "hi"}]))

    assert exc.value.code == "vision_gateway_disabled"


def test_is_provider_quota_error_detects_known_variants() -> None:
    from app.services.model_gateway import is_provider_quota_error

    assert is_provider_quota_error(RuntimeError("402 Insufficient Balance"))
    assert is_provider_quota_error(RuntimeError("insufficient_user_quota"))
    assert is_provider_quota_error(RuntimeError("exceeded_current_quota_error"))
    assert is_provider_quota_error(RuntimeError("rate_limit_reached_error"))
    assert not is_provider_quota_error(RuntimeError("connection reset by peer"))
    assert not is_provider_quota_error(RuntimeError("invalid api key"))
