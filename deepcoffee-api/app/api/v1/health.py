from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.common import DependencyHealthResponse, DependencyState, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", version=settings.app_version, time=datetime.now(timezone.utc))


@router.get("/health/dependencies", response_model=DependencyHealthResponse)
async def dependency_health(settings: Settings = Depends(get_settings)) -> DependencyHealthResponse:
    knowledge_dir = settings.resolved_knowledge_dir
    return DependencyHealthResponse(
        database=DependencyState(
            status="configured" if settings.database_url else "not_configured",
            detail="DATABASE_URL is set." if settings.database_url else "DATABASE_URL is not set.",
        ),
        new_api=DependencyState(
            status="configured" if settings.new_api_base_url else "not_configured",
            detail="NEW_API_BASE_URL is set." if settings.new_api_base_url else "NEW_API_BASE_URL is not set.",
        ),
        langfuse=DependencyState(
            status="configured" if settings.langfuse_public_key and settings.langfuse_secret_key else "not_configured",
            detail="Langfuse keys are set." if settings.langfuse_public_key and settings.langfuse_secret_key else "Langfuse keys are not set.",
        ),
        knowledge=DependencyState(
            status="ok" if knowledge_dir.exists() else "missing",
            detail=str(knowledge_dir),
        ),
    )
