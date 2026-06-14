"""Coffea 统一会话调度（coffea_dispatch）的请求/响应模型。

对应 docs/deepcoffee-ai-prompts.md §1。调度器输出只是「路由计划」，不直接入库；
会话状态统一在一个 session_id 命名空间下（见 §0 会话与多轮状态）。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# 响应里标注结果出自模型还是本地兜底（见 §0「输出来源标注」）。
SourceTag = Literal["model", "local", "mixed"]


class CoffeaAttachment(BaseModel):
    """一条附件（当前主要是图片）。

    附件是本轮原始输入的一部分，会随调度结果交给对应角色（冲煮教练、知识问答、联网核实或
    明确读图动作）自行判断是否有用。vision 通道（kimi-k2.6）**只收 base64**：前端传
    `data_url`（完整 `data:image/...;base64,...`）或 `image_base64` + `mime_type`。
    `url` 仅作记录，Moonshot 不接受纯 URL。
    """

    type: Literal["image"] = "image"
    ref: str | None = None  # 前端上传后回传的引用 id
    url: str | None = None  # 仅记录用；vision 通道不接受纯 URL
    data_url: str | None = None  # 完整 data URI：data:image/png;base64,xxxx
    image_base64: str | None = None  # 裸 base64（无前缀），配合 mime_type 拼 data URI
    mime_type: str | None = None  # 如 image/png、image/jpeg
    note: str | None = None  # 用户对该附件的文字说明


class CoffeaMessageRequest(BaseModel):
    message: str = Field(min_length=1, description="本轮用户自然语言消息")
    session_id: str | None = Field(default=None, description="续接已有会话；为空则后端新建")
    attachments: list[CoffeaAttachment] = Field(default_factory=list)


class CoffeaSessionState(BaseModel):
    """会话内维护的 active 实体与偏好。额外键放行，便于前向兼容。"""

    model_config = ConfigDict(extra="allow")

    active_bean_id: str | None = None
    active_recipe_id: str | None = None
    active_brew_id: str | None = None
    active_equipment_id: str | None = None


class DispatchPlan(BaseModel):
    """调度器输出的路由计划（模型或本地兜底产出，结构一致）。"""

    primary_intent: str
    secondary_intents: list[str] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    state_updates: dict[str, Any] = Field(default_factory=dict)
    direct_reply: str | None = Field(
        default=None,
        description="调度器自己可以直接回复用户的文本；它不是最终主回复，最终主回复由响应层 reply 承载。",
    )
    should_answer_directly: bool = False
    source: SourceTag = "model"
    # 模型路径失败回退本地时的原因标注（如 "provider_quota"=服务端模型 key 配额/欠费），
    # 响应层据此在 reply 里加显式提示，避免 AI 静默降级"变笨"。
    degrade_reason: str | None = None


class ActionResult(BaseModel):
    """执行一个动作后的结果。

    status：done（已执行出结果）/ degraded（能力在但降级，如图片通道未配）/
    pending（该能力后续阶段才接入）/ failed（执行报错）。
    """

    type: str
    status: Literal["done", "degraded", "pending", "failed"]
    source: SourceTag | None = None
    output: dict[str, Any] | None = None
    message: str | None = Field(
        default=None,
        description="单个动作产出的可读文本；它只是该动作的结果，不负责决定整轮最终主回复。",
    )


class CoffeaMessageResponse(BaseModel):
    session_id: str
    primary_intent: str
    secondary_intents: list[str] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    results: list[ActionResult] = Field(default_factory=list)
    state: CoffeaSessionState
    reply: str | None = Field(
        default=None,
        description="本轮最终展示给用户的主回复，由后端从 direct_reply 和 results[].message 中组装。",
    )
    should_answer_directly: bool = False
    source: SourceTag
    trace_id: str


class CoffeaSessionTurn(BaseModel):
    """聊天历史中的一轮（跨设备同步回看用）。"""

    role: str
    text: str | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)
    at: int | None = None


class CoffeaSessionHistory(BaseModel):
    """GET /coffea/session：该用户那条永久对话的完整历史。"""

    session_id: str
    state: CoffeaSessionState
    turns: list[CoffeaSessionTurn] = Field(default_factory=list)
