from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PublicEntity(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    canonical_name: str
    normalized_name: str
    scope: str
    status: str
    summary: str | None = None
    created_from: str
    created_at: datetime
    updated_at: datetime
    # 分类表的明细字段（roaster/origin/process… 各自补充），列表时可为空。
    detail: dict[str, Any] | None = None


class PublicEntityListResponse(BaseModel):
    items: list[PublicEntity]
    total: int
