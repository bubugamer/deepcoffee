from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.brew import BrewEvaluation

# 可选风味维度标签建议。无官方维度时不再自动生成默认维度。
DEFAULT_FLAVOR_LABELS = ["酸质", "甜感", "醇厚", "余韵", "发酵感"]


class FlavorAxis(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    value: float | None = Field(default=None, ge=0)


class BeanFlavor(BaseModel):
    """动态风味维度。axes 数量可变（建议 3–6 根），scale_max 是该套维度量表上限。"""

    notes: list[str] = Field(default_factory=list)
    source: Literal["roaster", "default", "user"] = "default"
    scale_max: float = Field(default=5, gt=0)
    axes: list[FlavorAxis] = Field(default_factory=list)
    # AI 解析时为每个风味词配的 emoji（note→emoji）；前端展示风味标签时取用，缺失则前端走内置词库。
    note_emojis: dict[str, str] = Field(default_factory=dict)


def default_flavor() -> BeanFlavor:
    return BeanFlavor(notes=[], source="default", scale_max=5, axes=[])


# 豆卡产品类型：单一豆源 / 拼配多豆源。系统按豆源条数自动写（1→single、≥2→blend），UI 不暴露。
BeanProductType = Literal["single", "blend"]


class BeanComponent(BaseModel):
    """一条「豆源」。单豆卡 1 条、拼配卡多条；豆子相关信息（产地/庄园/生豆商/处理法/品种/海拔/采收期）都在这里。"""

    origin_name: str | None = Field(default=None, max_length=160)
    coffee_source_name: str | None = Field(default=None, max_length=160)
    green_bean_merchant_name: str | None = Field(default=None, max_length=120)
    green_bean_product_name: str | None = Field(default=None, max_length=160)
    process_name: str | None = Field(default=None, max_length=120)
    varietal_names: list[str] = Field(default_factory=list)
    altitude_text: str | None = Field(default=None, max_length=120)
    harvest_date_text: str | None = Field(default=None, max_length=120)
    share_text: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=500)
    # 后端解析回填的公共实体 id（输入时忽略，由 beans._link_entities 写入）。
    origin_entity_id: str | None = None
    process_entity_id: str | None = None
    coffee_source_entity_id: str | None = None
    green_bean_merchant_entity_id: str | None = None
    varietal_entity_ids: list[str] = Field(default_factory=list)


class BeanDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=160)
    roaster_name: str | None = Field(default=None, max_length=120)
    roaster_product_name: str | None = Field(default=None, max_length=160)
    roast_date_text: str | None = Field(default=None, max_length=120)
    net_weight_text: str | None = Field(default=None, max_length=80)
    bean_components: list[BeanComponent] = Field(default_factory=list)
    flavor: BeanFlavor | None = None
    private_notes: str | None = Field(default=None, max_length=4000)
    public_comment: str | None = Field(default=None, max_length=1000)


class BeanParseRequest(BaseModel):
    input: str = Field(min_length=1, max_length=4000)
    source_type: str = "text"


class BeanParseResponse(BaseModel):
    draft: BeanDraft
    confidence: float
    low_confidence_fields: list[str]
    clarification: str | None = None
    source: Literal["model", "local"] = "local"  # 结果出自模型还是本地兜底（降级可见性）
    trace_id: str


class BeanConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: BeanDraft
    source_type: str = "text"
    raw_input: str | None = Field(default=None, max_length=4000)


class BeanConfirmResponse(BaseModel):
    bean_id: str
    trace_id: str


class BeanUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roaster_name: str | None = Field(default=None, max_length=120)
    roaster_product_name: str | None = Field(default=None, max_length=160)
    roast_date_text: str | None = Field(default=None, max_length=120)
    net_weight_text: str | None = Field(default=None, max_length=80)
    bean_components: list[BeanComponent] | None = None
    flavor: BeanFlavor | None = None
    rating: BrewEvaluation | None = None
    private_notes: str | None = Field(default=None, max_length=4000)
    public_comment: str | None = Field(default=None, max_length=1000)


class BeanRecommendedParams(BaseModel):
    """建议冲煮参数（始终对应一条冲煮记录，由 recommended_record_id 关联）。"""

    record_id: str | None = None
    record_type: str | None = None  # official_suggestion / ai_suggestion / user
    device: str | None = None
    grinder: str | None = None
    grind_setting: str | None = None
    dose_g: float | None = None
    water_ml: float | None = None
    water_temp_c: float | None = None
    ratio: str | None = None
    ratio_value: float | None = None
    brew_time_seconds: int | None = None


class Bean(BaseModel):
    bean_id: str
    name: str
    roaster: str | None = None
    roaster_entity_id: str | None = None  # 关联到的公共烘焙商实体（消歧聚合用）
    roaster_canonical: str | None = None  # 该实体的规范名（不同写法归一后的统一显示名）
    roaster_product: str | None = None
    coffee_source: str | None = None
    green_bean_merchant: str | None = None
    green_bean_product: str | None = None
    origin: str | None = None
    process: str | None = None
    varietal: list[str] = Field(default_factory=list)
    altitude_text: str | None = None
    harvest_date_text: str | None = None
    roast_date_text: str | None = None
    net_weight_text: str | None = None
    bean_components: list[BeanComponent] = Field(default_factory=list)
    bean_product_type: BeanProductType = "single"
    flavor: BeanFlavor
    rating: BrewEvaluation | None = None
    private_notes: str | None = None
    public_comment: str | None = None
    recommended_record_id: str | None = None
    recommended_params: BeanRecommendedParams | None = None
    avg_score: float | None = None
    record_count: int = 0
    created_at: datetime
    updated_at: datetime


class BeanListResponse(BaseModel):
    items: list[Bean]
    total: int


class SquareComment(BaseModel):
    """豆仓广场聚合条目下的一条匿名评论(来自某用户对该豆的公开评论)。"""

    comment: str
    overall_score: float | None = None
    created_at: datetime


class BeanSquareItem(BaseModel):
    bean_id: str
    name: str
    owner_count: int = 1  # 有多少位用户独立录入了这支豆(人气)
    comments: list[SquareComment] = Field(default_factory=list)  # 组内各家匿名评论(聚合)
    roaster: str | None = None
    roaster_canonical: str | None = None
    roaster_product: str | None = None
    coffee_source: str | None = None
    green_bean_merchant: str | None = None
    green_bean_product: str | None = None
    origin: str | None = None
    process: str | None = None
    varietal: list[str] = Field(default_factory=list)
    altitude_text: str | None = None
    harvest_date_text: str | None = None
    roast_date_text: str | None = None
    net_weight_text: str | None = None
    bean_components: list[BeanComponent] = Field(default_factory=list)
    bean_product_type: BeanProductType = "single"
    flavor: BeanFlavor
    rating: BrewEvaluation | None = None
    public_comment: str | None = None
    recommended_params: BeanRecommendedParams | None = None
    avg_score: float | None = None
    record_count: int = 0
    created_at: datetime
    updated_at: datetime


class BeanSquareListResponse(BaseModel):
    items: list[BeanSquareItem]
    total: int


class BeanSquareImportRequest(BaseModel):
    bean_ids: list[str] = Field(min_length=1, max_length=50)


class BeanSquareImportItem(BaseModel):
    source_bean_id: str
    bean_id: str
    status: Literal["created", "existing"]


class BeanSquareImportResponse(BaseModel):
    items: list[BeanSquareImportItem]
    created_count: int
    existing_count: int


class RecommendParamsResponse(BaseModel):
    recommended_params: BeanRecommendedParams
    recommended_record_id: str
    trace_id: str


class ManualRecommendParams(BaseModel):
    """手动编辑的建议冲煮参数（豆卡详情页编辑模式）。全部可选，落成隐藏 user_suggestion 记录。"""

    device: str | None = Field(default=None, max_length=120)
    grinder: str | None = Field(default=None, max_length=120)
    grind_setting: str | None = Field(default=None, max_length=120)
    dose_g: float | None = Field(default=None, ge=0, le=200)
    water_ml: float | None = Field(default=None, ge=0, le=5000)
    water_temp_c: float | None = Field(default=None, ge=50, le=100)
    ratio: str | None = Field(default=None, max_length=20)
    brew_time_seconds: int | None = Field(default=None, ge=0, le=3600)
    notes: str | None = Field(default=None, max_length=500)


class SetRecommendParamsRequest(BaseModel):
    """二选一：record_id（指向已有用户记录）或 params（手动参数，创建隐藏记录）。"""

    record_id: str | None = Field(default=None, min_length=1, max_length=64)
    params: ManualRecommendParams | None = None


# ---- Coffea 建议冲煮参数：多轮闭环（docs/deepcoffee-ai-prompts.md §5）----


class RecommendEquipment(BaseModel):
    brew_method: str | None = None  # 冲煮方式（下拉枚举）
    dripper: str | None = None  # 滤杯 / 冲煮器具
    grinder: str | None = None
    filter_media: str | None = None
    water: str | None = None


class RecommendationParams(BaseModel):
    """Coffea 在 completed 时给出的建议参数（校验后回前端展示）。"""

    device: str | None = None
    grinder: str | None = None
    filter: str | None = None
    dose_g: float | None = None
    water_ml: float | None = None
    water_temp_c: float | None = None
    ratio: str | None = None
    grind_setting: str | None = None
    brew_time_seconds: int | None = None
    notes: str | None = None


class RecommendParamsRequest(BaseModel):
    """多轮请求：带本轮用户消息 + 续接的 session_id（都可空：空消息= 让 Coffea 起手）。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str | None = Field(default=None, max_length=64)
    message: str | None = Field(default=None, max_length=4000)


class RecommendParamsTurnResponse(BaseModel):
    """多轮响应：status=needs_input / completed / fallback。"""

    status: Literal["needs_input", "completed", "fallback"]
    intent: str | None = None  # ask_equipment / generate_recommendation
    assistant_message: str
    session_id: str
    equipment: RecommendEquipment
    missing_fields: list[str] = Field(default_factory=list)
    recommendation: RecommendationParams | None = None
    recommended_record_id: str | None = None  # completed 时指向落库的隐藏 ai_suggestion 记录
    source: Literal["model", "local"] = "model"
    trace_id: str
