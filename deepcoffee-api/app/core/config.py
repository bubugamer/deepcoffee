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
    app_version: str = "0.1.0"
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

    new_api_base_url: str | None = Field(default=None, validation_alias=AliasChoices("NEW_API_BASE_URL", "DEEPCOFFEE_NEW_API_BASE_URL"))
    new_api_admin_token: str | None = Field(default=None, validation_alias=AliasChoices("NEW_API_ADMIN_TOKEN", "DEEPCOFFEE_NEW_API_ADMIN_TOKEN"))
    new_api_admin_user_id: str = Field(default="1", validation_alias=AliasChoices("NEW_API_ADMIN_USER_ID", "DEEPCOFFEE_NEW_API_ADMIN_USER_ID"))
    # new-api 的 quota 内部单位换算（默认 500000 quota = $1，与 new-api 默认一致）
    new_api_quota_per_unit: int = Field(default=500000, validation_alias=AliasChoices("NEW_API_QUOTA_PER_UNIT", "DEEPCOFFEE_NEW_API_QUOTA_PER_UNIT"))
    # 经 new-api 调用的默认模型名（需在 new-api 渠道里已启用）。见 docs/deepcoffee-ai-prompts.md §0。
    new_api_default_model: str = Field(default="deepseek-v4-pro", validation_alias=AliasChoices("NEW_API_DEFAULT_MODEL", "DEEPCOFFEE_NEW_API_DEFAULT_MODEL"))
    # 图片理解的 vision 通道模型名（独立模型，见 §2「外部依赖」）。默认 deepseek 纯文本不支持图片，
    # 故图片场景默认用 Moonshot `kimi-k2.6`（多模态，OpenAI 兼容，base64 走 image_url）。
    # 需在 new-api 渠道里启用该模型；渠道不可用时 image_understanding 整体降级，不影响纯文本能力。
    new_api_vision_model: str | None = Field(default="kimi-k2.6", validation_alias=AliasChoices("NEW_API_VISION_MODEL", "DEEPCOFFEE_NEW_API_VISION_MODEL"))
    # 新影子账户的初始配额（new-api 内部单位；500000 = $1）。Beta 先给一笔够用的；Phase 6 充值再调。
    new_api_initial_quota: int = Field(default=500000, validation_alias=AliasChoices("NEW_API_INITIAL_QUOTA", "DEEPCOFFEE_NEW_API_INITIAL_QUOTA"))

    @property
    def new_api_enabled(self) -> bool:
        return bool(self.new_api_base_url and self.new_api_admin_token)

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
