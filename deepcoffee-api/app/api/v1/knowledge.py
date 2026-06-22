from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_ai_quota, require_member
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import AuthenticatedUser, get_current_user
from app.models.tables import UserProfile
from app.repositories.knowledge_grants import knowledge_grant_repository
from app.repositories.profiles import profile_repository
from app.repositories.usage import ai_usage_repository
from app.services.ai_answer import answer_with_model
from app.schemas.knowledge import (
    ArticleDetail,
    ArticleSummary,
    CandidateFile,
    KnowledgeAskRequest,
    KnowledgeAskResponse,
    KnowledgeCategory,
    KnowledgeFileSelectRequest,
)
from app.services.knowledge_service import KnowledgeService, get_knowledge_service
from app.services.langfuse_client import langfuse_tracer
from app.services.entitlements import can_browse_knowledge, is_admin_user, require_knowledge_browse

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/categories", response_model=list[KnowledgeCategory])
async def list_categories(
    user: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> list[KnowledgeCategory]:
    profile = await session.get(UserProfile, user.id)
    require_knowledge_browse(profile.plan if profile else "basic", is_admin=is_admin_user(profile, user, settings))
    return service.list_categories()


@router.get("/articles", response_model=list[ArticleSummary])
async def list_articles(
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> list[ArticleSummary]:
    profile = await session.get(UserProfile, user.id)
    require_knowledge_browse(profile.plan if profile else "basic", is_admin=is_admin_user(profile, user, settings))
    return service.list_articles(category=category, q=q)


@router.get("/articles/{slug}", response_model=ArticleDetail)
async def get_article(
    slug: str,
    user: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> ArticleDetail:
    profile = await session.get(UserProfile, user.id)
    if not can_browse_knowledge(profile.plan if profile else "basic", is_admin=is_admin_user(profile, user, settings)):
        has_grant = await knowledge_grant_repository.has_grant(session, user_id=user.id, slug=slug)
        if not has_grant:
            raise AppError(403, "upgrade_required", "这篇文章尚未被 AI 引用，升级 Max 后可自由浏览知识库。")
    return service.get_article(slug)


@router.post("/ask", response_model=KnowledgeAskResponse, dependencies=[Depends(require_member), Depends(require_ai_quota)])
async def ask_knowledge(
    payload: KnowledgeAskRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: KnowledgeService = Depends(get_knowledge_service),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeAskResponse:
    await profile_repository.get_or_create(session, user.id, user.email)
    response = service.answer_question(payload.question)
    # 有模型用模型（基于本地选出的知识库摘录作答），失败即回退本地摘录式回答。
    model_used = False
    if response.from_knowledge_base:
        grounding = service.build_grounding([f.slug for f in response.selected_files], settings)
        failure_reasons: list[str] = []
        model_answer = await answer_with_model(
            payload.question,
            grounding,
            model=settings.model_default_model,
            failure_reasons=failure_reasons,
        )
        if model_answer:
            response.answer = model_answer
            model_used = True
        elif "provider_quota" in failure_reasons:
            # 服务端模型 key 配额/欠费导致的降级显式告知（本地检索答案仍然返回，不阻断问答）
            response.answer = f"{response.answer}\n\nAI 服务暂时不可用，本次为基础回复。"
    await ai_usage_repository.record(session, user_id=user.id, action="knowledge_ask", trace_id=response.trace_id)
    await knowledge_grant_repository.grant_many(
        session,
        user_id=user.id,
        slugs=[f.slug for f in response.selected_files],
        trace_id=response.trace_id,
    )
    langfuse_tracer.trace(
        "knowledge_answer",
        trace_id=response.trace_id,
        user_id=user.id,
        input=payload.question,
        output=response.answer,
        metadata={
            "from_knowledge_base": response.from_knowledge_base,
            "model_used": model_used,
            "model": settings.model_default_model if model_used else None,
            "selected_files": [f.slug for f in response.selected_files],
        },
    )
    return response


@router.post("/select-files", response_model=list[CandidateFile])
async def select_files(
    payload: KnowledgeFileSelectRequest,
    user: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> list[CandidateFile]:
    profile = await session.get(UserProfile, user.id)
    require_knowledge_browse(profile.plan if profile else "basic", is_admin=is_admin_user(profile, user, settings))
    candidates = service.select_files(payload.question)
    langfuse_tracer.trace(
        "knowledge_file_select",
        trace_id=f"kb_select_{uuid4().hex[:12]}",
        input=payload.question,
        output=[c.slug for c in candidates],
    )
    return candidates
