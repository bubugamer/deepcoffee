from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import AuthenticatedUser
from app.models.tables import UserProfile


PLAN_BASIC = "basic"
PLAN_PRO = "pro"
PLAN_MAX = "max"
VALID_PLANS = frozenset({PLAN_BASIC, PLAN_PRO, PLAN_MAX})


@dataclass(frozen=True)
class PlanDefinition:
    id: str
    name: str
    monthly_quota: int
    features: tuple[str, ...]


def normalize_plan(plan: str | None) -> str:
    value = (plan or PLAN_BASIC).lower()
    return value if value in VALID_PLANS else PLAN_BASIC


def plan_definitions(settings: Settings) -> dict[str, PlanDefinition]:
    return {
        PLAN_BASIC: PlanDefinition(
            id=PLAN_BASIC,
            name="Basic",
            monthly_quota=settings.ai_quota_basic,
            features=(
                f"AI 问答 {settings.ai_quota_basic} 次 / 月",
                "可使用 AI 知识库问答",
                "可打开 AI 引用文章",
            ),
        ),
        PLAN_PRO: PlanDefinition(
            id=PLAN_PRO,
            name="Pro",
            monthly_quota=settings.ai_quota_pro,
            features=(
                f"AI 问答 {settings.ai_quota_pro} 次 / 月",
                "可使用 AI 知识库问答",
                "可打开 AI 引用文章",
                "可查看同豆匿名冲煮记录",
                "可进入豆仓广场",
            ),
        ),
        PLAN_MAX: PlanDefinition(
            id=PLAN_MAX,
            name="Max",
            monthly_quota=settings.ai_quota_max,
            features=(
                f"AI 问答 {settings.ai_quota_max} 次 / 月",
                "包含 Pro 权益",
                "可自由浏览知识库",
            ),
        ),
    }


def quota_for_plan(plan: str | None, settings: Settings, custom_limit: int | None = None) -> int:
    if custom_limit is not None:
        return custom_limit
    return plan_definitions(settings)[normalize_plan(plan)].monthly_quota


def is_admin_user(profile: UserProfile | None, user: AuthenticatedUser, settings: Settings) -> bool:
    return user.id in settings.admin_user_ids or (profile is not None and profile.role == "admin")


def can_browse_knowledge(plan: str | None, *, is_admin: bool = False) -> bool:
    return is_admin or normalize_plan(plan) == PLAN_MAX


def can_use_bean_square(plan: str | None, *, is_admin: bool = False) -> bool:
    return is_admin or normalize_plan(plan) in {PLAN_PRO, PLAN_MAX}


def require_knowledge_browse(plan: str | None, *, is_admin: bool = False) -> None:
    if not can_browse_knowledge(plan, is_admin=is_admin):
        raise AppError(403, "upgrade_required", "升级 Max 后可自由浏览知识库。")


def require_bean_square(plan: str | None, *, is_admin: bool = False) -> None:
    if not can_use_bean_square(plan, is_admin=is_admin):
        raise AppError(403, "upgrade_required", "升级 Pro 后可使用豆仓广场与同豆冲煮参考。")
