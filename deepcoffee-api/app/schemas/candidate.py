from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class CandidateReviewRequest(BaseModel):
    reviewer_note: str | None = Field(default=None, max_length=1000)


class CandidatePromoteResponse(BaseModel):
    candidate_id: str
    proposal_id: str
    status: str
