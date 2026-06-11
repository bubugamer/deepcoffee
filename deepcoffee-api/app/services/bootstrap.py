from __future__ import annotations

import logging

from sqlalchemy import func, select

from app.core.config import Settings
from app.core.db import get_sessionmaker
from app.models.tables import InviteCode, UserProfile

logger = logging.getLogger(__name__)

BOOTSTRAP_NOTE = "bootstrap admin invite"


def normalized_bootstrap_code(settings: Settings) -> str | None:
    code = (settings.bootstrap_invite_code or "").strip().upper()
    return code or None


async def seed_bootstrap_invite_code(settings: Settings) -> None:
    """初始化邀请码落库（幂等）。

    守卫：只有 DB 里还没有任何 admin 时才注册——初始化一旦完成，后续部署
    生成的新码不再入库，避免 .env 里长期躺着一个能领管理员身份的码。
    """
    code = normalized_bootstrap_code(settings)
    if code is None:
        return
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        admin_count = await session.scalar(
            select(func.count()).select_from(UserProfile).where(UserProfile.role == "admin")
        )
        if admin_count:
            return
        if await session.get(InviteCode, code) is not None:
            return
        session.add(InviteCode(code=code, note=BOOTSTRAP_NOTE))
        await session.commit()
        logger.info("Bootstrap invite code registered; first registrant becomes admin.")
