from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EquipmentProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    brew_method: str | None = None
    grinder: str | None = None
    filter_media: str | None = None
    water: str | None = None
    label: str | None = None
    created_at: datetime
    updated_at: datetime


class EquipmentCreateRequest(BaseModel):
    brew_method: str | None = Field(default=None, max_length=120)
    grinder: str | None = Field(default=None, max_length=120)
    filter_media: str | None = Field(default=None, max_length=120)
    water: str | None = Field(default=None, max_length=120)
    label: str | None = Field(default=None, max_length=120)


class EquipmentUpdateRequest(BaseModel):
    brew_method: str | None = Field(default=None, max_length=120)
    grinder: str | None = Field(default=None, max_length=120)
    filter_media: str | None = Field(default=None, max_length=120)
    water: str | None = Field(default=None, max_length=120)
    label: str | None = Field(default=None, max_length=120)
