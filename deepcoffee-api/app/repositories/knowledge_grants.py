from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import UserKnowledgeArticleGrant


class KnowledgeGrantRepository:
    async def grant_many(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        slugs: list[str],
        trace_id: str | None = None,
    ) -> None:
        unique_slugs = sorted({slug.strip() for slug in slugs if slug and slug.strip()})
        if not unique_slugs:
            return
        values = [{"user_id": user_id, "slug": slug, "trace_id": trace_id} for slug in unique_slugs]
        stmt = insert(UserKnowledgeArticleGrant).values(values)
        stmt = stmt.on_conflict_do_nothing(index_elements=["user_id", "slug"])
        await session.execute(stmt)

    async def has_grant(self, session: AsyncSession, *, user_id: str, slug: str) -> bool:
        grant_id = await session.scalar(
            select(UserKnowledgeArticleGrant.id).where(
                UserKnowledgeArticleGrant.user_id == user_id,
                UserKnowledgeArticleGrant.slug == slug,
            )
        )
        return grant_id is not None


knowledge_grant_repository = KnowledgeGrantRepository()
