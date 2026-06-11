from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import InviteCode, UserProfile
from app.schemas.auth import InviteCodeInfo

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous chars


class InviteAlreadyUsedError(Exception):
    """尝试作废一个已被消费的邀请码。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _generate_code() -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"DC-{body[:4]}-{body[4:]}"


def _to_info(row: InviteCode, used_by_email: str | None = None) -> InviteCodeInfo:
    info = InviteCodeInfo.model_validate(row)
    info.used_by_email = used_by_email
    return info


@dataclass
class InviteRepository:
    """邀请码：校验 / 消费 / 管理员创建与列表。

    配置里的默认码（如 DEEP-BETA）视为可复用，不入库、不被消费——仅用于 dev / beta 体验。
    其余邀请码为管理员创建的 DB 行，消费后标记 used。
    """

    default_codes: set[str]

    async def validate(self, session: AsyncSession, code: str) -> bool:
        normalized = code.strip().upper()
        if normalized in self.default_codes:
            return True
        row = await session.get(InviteCode, normalized)
        if row is None:
            return False
        return self._is_usable(row)

    async def consume(self, session: AsyncSession, code: str, user_id: str) -> bool:
        normalized = code.strip().upper()
        if normalized in self.default_codes:
            return True  # reusable dev/beta code, not marked used
        row = await session.get(InviteCode, normalized)
        if row is None or not self._is_usable(row):
            return False
        row.status = "used"
        row.used_by = user_id
        row.used_at = datetime.now(timezone.utc)
        await session.flush()
        return True

    async def create_codes(
        self,
        session: AsyncSession,
        *,
        count: int,
        expires_at: datetime | None = None,
        note: str | None = None,
    ) -> list[InviteCodeInfo]:
        rows: list[InviteCode] = []
        for _ in range(count):
            row = InviteCode(code=_generate_code(), expires_at=expires_at, note=note)
            session.add(row)
            rows.append(row)
        await session.flush()
        for row in rows:
            await session.refresh(row)
        return [_to_info(row) for row in rows]

    async def revoke(self, session: AsyncSession, code: str) -> InviteCodeInfo | None:
        """作废一个未使用的邀请码。已用的码抛错（消费事实不可抹除）；重复作废幂等。"""
        row = await session.get(InviteCode, code.strip().upper())
        if row is None:
            return None
        if row.used_by is not None or row.status == "used":
            raise InviteAlreadyUsedError(row.code)
        if row.status != "revoked":
            row.status = "revoked"
            await session.flush()
        return _to_info(row)

    async def list(self, session: AsyncSession, *, status: str | None = None) -> list[InviteCodeInfo]:
        conditions = []
        if status:
            conditions.append(InviteCode.status == status)
        # LEFT JOIN user_profiles：把消费者 uid（used_by）解析成可读邮箱，供管理员页展示。
        result = await session.execute(
            select(InviteCode, UserProfile.email)
            .outerjoin(UserProfile, InviteCode.used_by == UserProfile.id)
            .where(*conditions)
            .order_by(InviteCode.created_at.desc())
        )
        return [_to_info(row, email) for row, email in result.all()]

    @staticmethod
    def _is_usable(row: InviteCode) -> bool:
        if row.status != "active" or row.used_by is not None:
            return False
        if row.expires_at is not None and row.expires_at <= datetime.now(timezone.utc):
            return False
        return True
