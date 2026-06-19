from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BrewParseRequest(BaseModel):
    input: str = Field(min_length=1, max_length=4000)
    source_type: str = "text"


class BrewStep(BaseModel):
    time_seconds: int = Field(ge=0)
    action: str = Field(min_length=1, max_length=200)
    water_ml: float | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=500)


class BrewEvaluationItem(BaseModel):
    score: int | None = Field(default=None, ge=1, le=5)
    description: str | None = Field(default=None, max_length=1000)


class BrewEvaluation(BaseModel):
    overall: BrewEvaluationItem | None = None
    aroma: BrewEvaluationItem | None = None
    flavor: BrewEvaluationItem | None = None
    aftertaste: BrewEvaluationItem | None = None
    acidity: BrewEvaluationItem | None = None
    body: BrewEvaluationItem | None = None
    balance: BrewEvaluationItem | None = None


class BrewDraft(BaseModel):
    bean_name: str | None = Field(default=None, max_length=160)
    origin: str | None = Field(default=None, max_length=120)
    roaster: str | None = Field(default=None, max_length=120)
    process: str | None = Field(default=None, max_length=120)
    varietal: str | None = Field(default=None, max_length=120)
    brew_method: str | None = Field(default=None, max_length=120)
    device: str | None = Field(default=None, max_length=120)
    grinder: str | None = Field(default=None, max_length=120)
    grind_setting: str | None = Field(default=None, max_length=80)
    filter_media: str | None = Field(default=None, max_length=120)
    water: str | None = Field(default=None, max_length=120)
    dose_g: float | None = Field(default=None, gt=0)
    water_ml: float | None = Field(default=None, gt=0)
    water_temp_c: float | None = Field(default=None, gt=0)
    ratio: str | None = Field(default=None, max_length=40)
    ratio_value: float | None = Field(default=None, gt=0)
    brew_time: str | None = Field(default=None, max_length=40)
    brew_time_seconds: int | None = Field(default=None, gt=0)
    brew_steps: list[BrewStep] = Field(default_factory=list)
    evaluation: BrewEvaluation | None = None
    notes: str | None = Field(default=None, max_length=4000)


class BrewParseResponse(BaseModel):
    draft: BrewDraft
    confidence: float
    low_confidence_fields: list[str]
    clarification: str | None = None
    source: Literal["model", "local"] = "local"
    trace_id: str


class BrewConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: BrewDraft
    source_type: str = "text"
    raw_input: str | None = Field(default=None, max_length=4000)
    # 可选：从豆仓某张豆卡发起冲煮时带上，记录会挂到该豆子（同豆聚合 / 反向更新建议参数）。
    bean_card_id: str | None = Field(default=None, max_length=64)


class BrewConfirmResponse(BaseModel):
    brew_id: str
    recap: str
    suggestions: list[str]
    source: Literal["model", "local"] = "local"
    trace_id: str


class BrewRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    # 归属：user（用户自己）/ official_suggestion / ai_suggestion；后两类 is_user_visible=False。
    bean_card_id: str | None = None
    record_type: str = "user"
    is_user_visible: bool = True
    source_type: str
    raw_input: str | None = None
    bean_name: str | None = None
    origin: str | None = None
    roaster: str | None = None
    process: str | None = None
    varietal: str | None = None
    brew_method: str | None = None
    device: str | None = None
    grinder: str | None = None
    grind_setting: str | None = None
    filter_media: str | None = None
    water: str | None = None
    dose_g: float | None = None
    water_ml: float | None = None
    water_temp_c: float | None = None
    ratio: str | None = None
    ratio_value: float | None = None
    brew_time: str | None = None
    brew_time_seconds: int | None = None
    brew_steps: list[BrewStep]
    evaluation: BrewEvaluation | None = None
    notes: str | None = None
    recap: str | None = None
    suggestions: list[str]
    trace_id: str | None = None
    created_at: datetime
    updated_at: datetime


class BrewRecordListResponse(BaseModel):
    items: list[BrewRecord]
    page: int
    page_size: int
    total: int


class BrewRecordUpdateRequest(BaseModel):
    bean_name: str | None = None
    origin: str | None = None
    roaster: str | None = None
    process: str | None = None
    varietal: str | None = None
    brew_method: str | None = None
    device: str | None = None
    grinder: str | None = None
    grind_setting: str | None = None
    filter_media: str | None = None
    water: str | None = None
    dose_g: float | None = Field(default=None, gt=0)
    water_ml: float | None = Field(default=None, gt=0)
    water_temp_c: float | None = Field(default=None, gt=0)
    ratio: str | None = None
    ratio_value: float | None = Field(default=None, gt=0)
    brew_time: str | None = None
    brew_time_seconds: int | None = Field(default=None, gt=0)
    brew_steps: list[BrewStep] | None = None
    evaluation: BrewEvaluation | None = None
    notes: str | None = None


class BrewDeleteResponse(BaseModel):
    deleted: bool


class BrewComparisonItem(BaseModel):
    id: str
    date: str
    bean_name: str | None = None
    device: str | None = None
    grinder: str | None = None
    grind_setting: str | None = None
    dose_g: float | None = None
    water_ml: float | None = None
    ratio: str | None = None
    ratio_value: float | None = None
    water_temp_c: float | None = None
    brew_time_seconds: int | None = None
    overall_score: int | None = None
    active: bool = False
