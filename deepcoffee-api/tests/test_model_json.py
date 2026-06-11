from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.services.model_json import (
    ModelJSONError,
    chat_json,
    check_number_in_range,
    extract_json_object,
    require_keys,
    whitelist_keys,
)


# --- extract_json_object ----------------------------------------------------

def test_extract_plain_object() -> None:
    assert extract_json_object('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_extract_strips_code_fence() -> None:
    # 模型偶尔不听话加 ```json 围栏，要能剥掉。
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_tolerates_surrounding_text() -> None:
    assert extract_json_object('好的：{"a": 1} 以上。') == {"a": 1}


def test_extract_empty_raises() -> None:
    with pytest.raises(ModelJSONError):
        extract_json_object("   ")


def test_extract_invalid_json_raises() -> None:
    with pytest.raises(ModelJSONError):
        extract_json_object("not json at all")


def test_extract_non_object_raises() -> None:
    with pytest.raises(ModelJSONError):
        extract_json_object("[1, 2, 3]")


# --- require_keys / whitelist_keys -----------------------------------------

def test_require_keys_missing_raises() -> None:
    with pytest.raises(ModelJSONError):
        require_keys({"a": 1}, ["a", "b"])


def test_require_keys_ok() -> None:
    require_keys({"a": 1, "b": 2}, ["a", "b"])  # no raise


def test_whitelist_drops_extra() -> None:
    assert whitelist_keys({"a": 1, "x": 9}, ["a"]) == {"a": 1}


def test_whitelist_strict_raises_on_extra() -> None:
    with pytest.raises(ModelJSONError):
        whitelist_keys({"a": 1, "x": 9}, ["a"], strict=True)


# --- check_number_in_range --------------------------------------------------

def test_range_ok() -> None:
    assert check_number_in_range(92, field="water_temp_c", low=85, high=96) == 92.0


def test_range_out_raises() -> None:
    with pytest.raises(ModelJSONError):
        check_number_in_range(120, field="water_temp_c", low=85, high=96)


def test_range_none_allowed() -> None:
    assert check_number_in_range(None, field="x", low=0, high=1, allow_none=True) is None


def test_range_none_not_allowed_raises() -> None:
    with pytest.raises(ModelJSONError):
        check_number_in_range(None, field="x", low=0, high=1)


def test_range_bool_rejected() -> None:
    # bool 是 int 的子类，但不是有效数值。
    with pytest.raises(ModelJSONError):
        check_number_in_range(True, field="x", low=0, high=10)


def test_range_string_rejected() -> None:
    with pytest.raises(ModelJSONError):
        check_number_in_range("92", field="x", low=85, high=96)


# --- chat_json --------------------------------------------------------------

class _FakeGateway:
    """记录调用参数、返回预置内容的假网关。"""

    def __init__(self, content: str) -> None:
        self.content = content
        self.last_kwargs: dict = {}

    async def chat(self, **kwargs):  # noqa: ANN003
        self.last_kwargs = kwargs
        return SimpleNamespace(content=self.content, model="fake")


def test_chat_json_parses_and_passes_response_format() -> None:
    gw = _FakeGateway('{"status": "ok", "n": 1}')
    data = asyncio.run(
        chat_json(
            gw,
            user_token="sk-x",
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            required_keys=["status"],
            allowed_keys=["status", "n"],
        )
    )
    assert data == {"status": "ok", "n": 1}
    # 必须以 JSON 模式调用底层网关。
    assert gw.last_kwargs["response_format"] == {"type": "json_object"}


def test_chat_json_raises_on_missing_required_key() -> None:
    gw = _FakeGateway('{"n": 1}')
    with pytest.raises(ModelJSONError):
        asyncio.run(
            chat_json(
                gw,
                user_token="sk-x",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                required_keys=["status"],
            )
        )


def test_chat_json_whitelist_drops_extra_keys() -> None:
    gw = _FakeGateway('{"a": 1, "evil": 2}')
    data = asyncio.run(
        chat_json(
            gw,
            user_token="sk-x",
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            allowed_keys=["a"],
        )
    )
    assert data == {"a": 1}
