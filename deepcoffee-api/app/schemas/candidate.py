from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SimilarEntity(BaseModel):
    """审核时提示的「疑似已有实体」（不自动合，供管理员决定是否并入）。"""

    id: str
    entity_type: str
    canonical_name: str
    status: str


class CandidateFact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    fact_type: str | None = None
    title: str
    payload: dict[str, Any]
    source_scope: str
    source_table: str | None = None
    source_record_id: str | None = None
    source_user_id: str | None = None
    status: str
    proposed_entity_id: str | None = None
    proposal_id: str | None = None
    reviewer_note: str | None = None
    trace_id: str | None = None
    created_at: datetime
    updated_at: datetime
    # 审核辅助：疑似已有实体（不自动合，供管理员「并入」决策）。非 ORM 字段，由 API 填充。
    similar_entities: list[SimilarEntity] = Field(default_factory=list)


class CandidateMergeRequest(BaseModel):
    entity_id: str = Field(min_length=1, description="并入的目标已有实体 id")
    reviewer_note: str | None = Field(default=None, max_length=1000)


class CandidateReviewRequest(BaseModel):
    reviewer_note: str | None = Field(default=None, max_length=1000)


class CandidatePromoteResponse(BaseModel):
    candidate_id: str
    proposal_id: str
    status: str
