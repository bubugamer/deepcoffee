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
