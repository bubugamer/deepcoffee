from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    # 多语言显示名（阶段 2）：display_name 按请求语言取，取不到回退 canonical_name；
    # localized_names = {locale: 名字}，来自带 locale 的别名，供管理/前端按语言展示。
    display_name: str | None = None
    localized_names: dict[str, str] = Field(default_factory=dict)


class PublicEntityListResponse(BaseModel):
    items: list[PublicEntity]
    total: int


# ---- 阶段 4：管理员合并 / 规范主名 ----


class EntityMergeRequest(BaseModel):
    target_id: str = Field(min_length=1, description="并入的目标实体 id（当前实体并入它）")
    reviewer_note: str | None = Field(default=None, max_length=1000)


class EntityRenameRequest(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=200, description="规范后的单一干净主名")
    reviewer_note: str | None = Field(default=None, max_length=1000)


class DuplicateGroup(BaseModel):
    reason: str  # form（形态相同）/ substring（缩写↔全称）
    entities: list[PublicEntity]


class EntityDuplicatesResponse(BaseModel):
    groups: list[DuplicateGroup]
    mixed_names: list[PublicEntity]  # 仍是混合主名、建议规范成单一主名的实体
