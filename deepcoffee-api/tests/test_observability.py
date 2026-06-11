from __future__ import annotations

from types import SimpleNamespace

from app.core.observability import init_observability
from app.services.langfuse_client import LangfuseTracer


def _tracer(**overrides) -> LangfuseTracer:
    # config 字段有 validation_alias，按字段名传 Settings(...) 不生效；这里直接喂 tracer
    # 需要的几个属性即可（避免依赖 .env / 别名）。
    base = dict(
        langfuse_public_key=None,
        langfuse_secret_key=None,
        langfuse_host=None,
        log_full_ai_io=False,
    )
    base.update(overrides)
    return LangfuseTracer(SimpleNamespace(**base))


def test_tracer_disabled_without_keys_is_noop() -> None:
    tracer = _tracer()
    assert tracer.enabled is False
    # 未配置时 trace() 是空操作，绝不抛异常。
    tracer.trace("brew_parse", trace_id="t1", user_id="u1", input="some input", output={"ok": True})


def test_tracer_enabled_when_all_keys_present() -> None:
    tracer = _tracer(
        langfuse_public_key="pk", langfuse_secret_key="sk", langfuse_host="http://localhost:3001"
    )
    assert tracer.enabled is True


def test_mask_redacts_io_when_full_logging_off() -> None:
    tracer = _tracer()
    masked = tracer._mask_value("a long prompt with private content")
    assert masked == {"chars": len("a long prompt with private content"), "redacted": True}


def test_mask_passthrough_when_full_logging_on() -> None:
    tracer = _tracer(log_full_ai_io=True)
    assert tracer._mask_value("keep me") == "keep me"


def test_metadata_strips_sensitive_keys() -> None:
    tracer = _tracer(log_full_ai_io=True)
    cleaned = tracer._mask_metadata({"model": "deepseek", "internal_token": "sk-secret"})
    assert cleaned["model"] == "deepseek"
    assert cleaned["internal_token"] == {"redacted": True}


def test_sentry_init_noop_without_dsn() -> None:
    # 没配 DSN 时 init 应安静返回（不初始化 Sentry，不报错）。
    init_observability(SimpleNamespace(sentry_dsn=None))
