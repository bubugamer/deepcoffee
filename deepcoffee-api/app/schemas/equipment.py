from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


EquipmentCategory = Literal["brewer", "grinder", "filter_media", "water"]


class EquipmentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category: EquipmentCategory
    name: str
    notes: str | None = None
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


class EquipmentCreateRequest(BaseModel):
    category: EquipmentCategory
    name: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=500)
    is_default: bool | None = None


class EquipmentUpdateRequest(BaseModel):
    category: EquipmentCategory | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=500)
    is_default: bool | None = None
