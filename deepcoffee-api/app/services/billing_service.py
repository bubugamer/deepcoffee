"""Billing service: 影子计费账户与额度/用量读取。

未配置 new-api 时全部回退到本地行为（额度本地计数、用量为空），不影响现有流程与测试。
配置 new-api 后：为用户建影子账户 + 内部 token，额度/用量从 new-api 读取。
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.tables import NewapiBillingLink
from app.schemas.auth import UserQuota
from app.schemas.billing import UsageSummary
from app.services.newapi_client import NewApiClient, NewApiError

logger = logging.getLogger(__name__)


class BillingService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return self.settings.new_api_enabled

    async def get_link(self, session: AsyncSession, user_id: str) -> NewapiBillingLink | None:
        if not self.enabled:
            return None
        return await session.get(NewapiBillingLink, user_id)

    async def get_model_token(self, session: AsyncSession, user_id: str) -> str | None:
        """取用户的模型调用 token（sk-...）。没配 new-api / 没影子账户 / 没 token 都返回 None。"""
        link = await self.get_link(session, user_id)
        return link.internal_token if link else None

    async def ensure_shadow_account(
        self, session: AsyncSession, user_id: str, email: str | None = None, plan: str = "basic"
    ) -> NewapiBillingLink | None:
        """为用户创建 new-api 影子账户 + 内部 token（幂等）。new-api 未配置则 no-op。"""
        if not self.enabled:
            return None
        existing = await session.get(NewapiBillingLink, user_id)
        if existing is not None:
            return existing

        client = NewApiClient(self.settings)
        # new-api 用户名要唯一且 ≤12 字符；用随机短串避免 uuid 截断撞名（映射靠 newapi_user_id 存）。
        username = "dc" + secrets.token_hex(5)  # 12 字符
        password = secrets.token_urlsafe(12)  # 16 字符（new-api 密码限 8–20 位）
        # display_name 用短用户名：new-api 对 DisplayName 有 max 长度校验，邮箱会超长被拒；
        # 真实邮箱存在我们自己的 UserProfile，new-api 侧只是内部影子账户，无需用邮箱。
        try:
            user = await client.create_user(username=username, password=password, display_name=username)
            newapi_user_id = str(user.get("id"))
        except NewApiError as exc:
            # 建用户失败不应阻断用户使用；记日志，下次再试。
            logger.warning("ensure_shadow_account: create user failed for %s: %s", user_id, exc.message)
            return None
        # 授初始配额：new-api 新用户默认 quota=0，不授额模型调用会报 insufficient_user_quota。
        try:
            await client.set_user_quota(newapi_user_id, quota=self.settings.new_api_initial_quota)
        except NewApiError as exc:
            logger.warning("ensure_shadow_account: grant quota failed for %s: %s", user_id, exc.message)
        # 模型调用 token 是 self 路由、需该用户登录创建，暂为 best-effort：
        # 失败不阻断（读余额/用量只需 newapi_user_id）；Phase 4 接真模型调用时补齐 token。
        token: str | None = None
        try:
            token = await client.create_api_token(username=username, password=password)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ensure_shadow_account: token deferred for %s: %s", user_id, exc)

        link = NewapiBillingLink(
            user_id=user_id,
            newapi_user_id=newapi_user_id,
            internal_token=token,
            plan=plan,
            last_synced_at=datetime.now(timezone.utc),
        )
        session.add(link)
        await session.flush()
        return link

    async def get_quota(self, session: AsyncSession, user_id: str, *, local_quota: UserQuota) -> UserQuota:
        """额度：配了 new-api 且有影子账户就读 new-api，否则用传入的本地额度。"""
        link = await self.get_link(session, user_id)
        if link is None:
            return local_quota
        try:
            user = await NewApiClient(self.settings).get_user(link.newapi_user_id)
        except NewApiError:
            return local_quota
        per_unit = self.settings.new_api_quota_per_unit or 500000
        quota = int(user.get("quota", 0) or 0)
        used = int(user.get("used_quota", 0) or 0)
        balance = max(0.0, (quota - used) / per_unit)
        return UserQuota(
            plan=link.plan,
            balance=round(balance, 4),
            ai_used=int(user.get("request_count", local_quota.ai_used) or 0),
            ai_total=local_quota.ai_total,
            reset_at=local_quota.reset_at,
            features=local_quota.features,
        )

    async def get_usage(self, session: AsyncSession, user_id: str) -> UsageSummary:
        link = await self.get_link(session, user_id)
        if link is None:
            return UsageSummary(total_tokens=0, total_requests=0, total_cost=0, by_model=[])
        try:
            user = await NewApiClient(self.settings).get_user(link.newapi_user_id)
        except NewApiError:
            return UsageSummary(total_tokens=0, total_requests=0, total_cost=0, by_model=[])
        per_unit = self.settings.new_api_quota_per_unit or 500000
        return UsageSummary(
            total_tokens=int(user.get("used_quota", 0) or 0),
            total_requests=int(user.get("request_count", 0) or 0),
            total_cost=round(int(user.get("used_quota", 0) or 0) / per_unit, 4),
            by_model=[],
        )

    async def sync(self, session: AsyncSession, user_id: str) -> dict[str, str]:
        if not self.enabled:
            return {"status": "skipped", "reason": "new-api is not connected yet"}
        link = await self.get_link(session, user_id)
        if link is None:
            return {"status": "skipped", "reason": "no shadow account; will be created on next active request"}
        link.last_synced_at = datetime.now(timezone.utc)
        await session.flush()
        return {"status": "synced"}


billing_service = BillingService()
