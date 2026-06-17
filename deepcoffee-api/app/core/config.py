from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "DeepCoffee API"
    app_version: str = "0.16.0"
    app_env: str = Field(default="local", validation_alias=AliasChoices("DEEPCOFFEE_APP_ENV", "APP_ENV"))
    api_prefix: str = "/v1"
    docs_enabled: bool = True

    repo_root: Path = Field(default_factory=default_repo_root)
    knowledge_dir: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("DEEPCOFFEE_KNOWLEDGE_DIR", "KNOWLEDGE_DIR"),
    )

    # 知识库问答 grounding（喂模型的整篇正文）长度护栏。
    kb_grounding_docs: int = Field(default=3, validation_alias=AliasChoices("KB_GROUNDING_DOCS", "DEEPCOFFEE_KB_GROUNDING_DOCS"))
    kb_max_chars_per_doc: int = Field(default=6000, validation_alias=AliasChoices("KB_MAX_CHARS_PER_DOC", "DEEPCOFFEE_KB_MAX_CHARS_PER_DOC"))
    kb_max_context_chars: int = Field(default=14000, validation_alias=AliasChoices("KB_MAX_CONTEXT_CHARS", "DEEPCOFFEE_KB_MAX_CONTEXT_CHARS"))

    backend_cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
        validation_alias=AliasChoices("DEEPCOFFEE_BACKEND_CORS_ORIGINS", "BACKEND_CORS_ORIGINS"),
    )

    database_url: str | None = Field(default=None, validation_alias=AliasChoices("DATABASE_URL", "DEEPCOFFEE_DATABASE_URL"))
    supabase_database_url: str | None = Field(
        default=None, validation_alias=AliasChoices("SUPABASE_DATABASE_URL", "DEEPCOFFEE_SUPABASE_DATABASE_URL")
    )
    supabase_url: str | None = Field(default=None, validation_alias=AliasChoices("SUPABASE_URL", "DEEPCOFFEE_SUPABASE_URL"))
    supabase_jwt_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_JWT_SECRET", "DEEPCOFFEE_SUPABASE_JWT_SECRET"),
    )
    supabase_jwt_algorithms: str = "HS256"
    supabase_jwks_url: str | None = Field(
        default=None, validation_alias=AliasChoices("SUPABASE_JWKS_URL", "DEEPCOFFEE_SUPABASE_JWKS_URL")
    )
    supabase_secret_key: str | None = Field(
        default=None, validation_alias=AliasChoices("SUPABASE_SECRET_KEY", "DEEPCOFFEE_SUPABASE_SECRET_KEY")
    )

    # OpenAI-compatible model gateway. DeepCoffee owns user quota; model calls use
    # this server-side key and never create per-user provider keys.
    model_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEEPCOFFEE_MODEL_BASE_URL", "MODEL_BASE_URL"),
    )
    model_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEEPCOFFEE_MODEL_API_KEY", "MODEL_API_KEY"),
    )
    model_default_model: str = Field(
        default="deepseek-v4-pro",
        validation_alias=AliasChoices("DEEPCOFFEE_MODEL_DEFAULT_MODEL", "MODEL_DEFAULT_MODEL"),
    )
    # Optional independent OpenAI-compatible vision channel.
    vision_model_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEEPCOFFEE_VISION_MODEL_BASE_URL", "VISION_MODEL_BASE_URL"),
    )
    vision_model_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEEPCOFFEE_VISION_MODEL_API_KEY", "VISION_MODEL_API_KEY"),
    )
    vision_model: str | None = Field(
        default="kimi-k2.6",
        validation_alias=AliasChoices("DEEPCOFFEE_VISION_MODEL", "VISION_MODEL"),
    )
    # 思考类模型（如 deepseek-v4-pro / kimi-k2.6）默认开「思考」：单次几十秒（超前端等待）、把
    # max_tokens 预算吃光导致正文为空、且只接受 temperature=1。置 true 让网关下发
    # {"thinking": {"type": "disabled"}} 关掉思考——实测变 1~3 秒、正文完整、temperature 也恢复可用。
    model_disable_thinking: bool = Field(
        default=False,
        validation_alias=AliasChoices("DEEPCOFFEE_MODEL_DISABLE_THINKING", "MODEL_DISABLE_THINKING"),
    )
    vision_model_disable_thinking: bool = Field(
        default=False,
        validation_alias=AliasChoices("DEEPCOFFEE_VISION_MODEL_DISABLE_THINKING", "VISION_MODEL_DISABLE_THINKING"),
    )
    # 对话豆卡识图自动录入的识别度阈值：综合识别度（vision 自报与字段完整度取 min）达到即直接建档，
    # 低于则出草稿卡让用户确认。
    bean_card_autosave_confidence: float = Field(default=0.8, validation_alias=AliasChoices("DEEPCOFFEE_BEAN_CARD_AUTOSAVE_CONFIDENCE", "BEAN_CARD_AUTOSAVE_CONFIDENCE"))

    @property
    def model_gateway_enabled(self) -> bool:
        return bool(self.model_base_url and self.model_api_key)

    @property
    def vision_gateway_enabled(self) -> bool:
        return bool(self.vision_model_base_url and self.vision_model_api_key and self.vision_model)

    # 联网核实 web_verify（§9）：Brave Search API。未配 key 时 web_verify 整体降级回知识库。
    brave_api_key: str | None = Field(default=None, validation_alias=AliasChoices("BRAVE_API_KEY", "DEEPCOFFEE_BRAVE_API_KEY"))
    brave_search_count: int = Field(default=5, validation_alias=AliasChoices("BRAVE_SEARCH_COUNT", "DEEPCOFFEE_BRAVE_SEARCH_COUNT"))

    @property
    def web_search_enabled(self) -> bool:
        return bool(self.brave_api_key)

    sentry_dsn: str | None = Field(default=None, validation_alias=AliasChoices("SENTRY_DSN", "DEEPCOFFEE_SENTRY_DSN"))
    langfuse_public_key: str | None = Field(default=None, validation_alias=AliasChoices("LANGFUSE_PUBLIC_KEY", "DEEPCOFFEE_LANGFUSE_PUBLIC_KEY"))
    langfuse_secret_key: str | None = Field(default=None, validation_alias=AliasChoices("LANGFUSE_SECRET_KEY", "DEEPCOFFEE_LANGFUSE_SECRET_KEY"))
    langfuse_host: str | None = Field(default=None, validation_alias=AliasChoices("LANGFUSE_HOST", "DEEPCOFFEE_LANGFUSE_HOST"))
    log_full_ai_io: bool = Field(default=False, validation_alias=AliasChoices("DEEPCOFFEE_LOG_FULL_AI_IO", "LOG_FULL_AI_IO"))

    admin_user_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias=AliasChoices("DEEPCOFFEE_ADMIN_USER_IDS", "ADMIN_USER_IDS"),
    )
    # 初始化邀请码（部署时随机生成写入 .env）：仅当 DB 里还没有任何 admin 时，启动会把它
    # 注册为一次性邀请码；用它完成注册的用户自动成为管理员。初始化完成后该配置即失效。
    bootstrap_invite_code: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEEPCOFFEE_BOOTSTRAP_INVITE_CODE", "BOOTSTRAP_INVITE_CODE"),
    )
    # 后端强制邀请门禁：业务接口要求用户已消费过邀请码（或为 admin），否则 403 invite_required。
    # 本地用 dev token 调业务接口时可临时关掉（false），生产保持 true。
    enforce_invite_gate: bool = Field(
        default=True,
        validation_alias=AliasChoices("DEEPCOFFEE_ENFORCE_INVITE_GATE", "ENFORCE_INVITE_GATE"),
    )
    # 邀请码注册制：默认不预置任何「万能码」。所有邀请码须经 POST /v1/admin/invites 生成，
    # 天然一次性（消费即标记 used）。dev/beta 如需临时复用码，可显式配 DEEPCOFFEE_DEFAULT_INVITE_CODES。
    default_invite_codes: list[str] = Field(default_factory=list)

    # Basic 套餐每月 AI 问答次数上限（真门禁阈值，同时作为 /me/quota、/billing/plans 的展示数）。
    # Pro 视为无限。放进 Settings 便于按环境调参与测试覆写。
    ai_quota_basic: int = Field(default=500, validation_alias=AliasChoices("DEEPCOFFEE_AI_QUOTA_BASIC", "AI_QUOTA_BASIC"))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DEEPCOFFEE_",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("backend_cors_origins", "admin_user_ids", mode="before")
    @classmethod
    def parse_string_list(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    @property
    def resolved_knowledge_dir(self) -> Path:
        if self.knowledge_dir is None:
            return self.repo_root / "knowledge"
        if self.knowledge_dir.is_absolute():
            return self.knowledge_dir
        return (self.repo_root / self.knowledge_dir).resolve()

    @property
    def jwt_algorithms(self) -> list[str]:
        return [item.strip() for item in self.supabase_jwt_algorithms.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
