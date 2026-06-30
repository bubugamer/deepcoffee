from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GiftPlan = Literal["pro", "max"]
GiftDurationMonths = Literal[1, 3, 6, 12]


class InviteValidateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)


class InviteValidateResponse(BaseModel):
    valid: bool
    message: str
    # 该码兑换后赠送的会员等级与时长（供注册页预览；无赠送则为 None）。
    gift_plan: str | None = None
    gift_duration_months: int | None = None


class InviteRedeemRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)


class InviteRedeemResponse(BaseModel):
    redeemed: bool
    message: str


class InviteCodeInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    status: str
    expires_at: datetime | None = None
    note: str | None = None
    gift_plan: str | None = None
    gift_duration_months: int | None = None
    used_by: str | None = None
    used_by_email: str | None = None
    used_at: datetime | None = None
    created_at: datetime


class InviteCreateRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=100)
    expires_at: datetime | None = None
    note: str | None = Field(default=None, max_length=200)
    # 公测：每个邀请码即一张会员赠送券，生成时必须指定赠什么 + 赠多久。
    gift_plan: GiftPlan = "pro"
    gift_duration_months: GiftDurationMonths = 1


class UserProfile(BaseModel):
    id: str
    email: str | None = None
    display_name: str | None = None
    plan: str = "basic"
    plan_source: str = "manual"
    plan_expires_at: datetime | None = None
    role: str = "user"
    status: str = "active"
    # 是否已绑定邀请码（或被门禁豁免）。False 时前端弹「补填邀请码」。
    invite_bound: bool = True
    timezone: str = "Asia/Shanghai"
    unit_system: str = "metric"
    created_at: datetime


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    timezone: str | None = Field(default=None, max_length=80)
    unit_system: str | None = Field(default=None, pattern="^(metric|imperial)$")


class UserQuota(BaseModel):
    plan: str
    balance: float
    ai_used: int
    ai_total: int | None
    ai_remaining: int | None
    reset_at: datetime | None
    features: list[str]


class AdminUserInfo(BaseModel):
    """管理员视角：注册用户 + 其所绑定的邀请码（按用户维度看注册来源）。"""

    id: str
    email: str | None = None
    display_name: str | None = None
    plan: str
    plan_source: str = "manual"
    plan_expires_at: datetime | None = None
    role: str = "user"
    status: str = "active"
    created_at: datetime
    invite_code: str | None = None
    invited_at: datetime | None = None
    ai_used: int = 0
    ai_total: int | None = None
    ai_remaining: int | None = None
    quota_custom: bool = False


class AdminUserUpdateRequest(BaseModel):
    """管理员对用户的操作：改套餐 / 任免管理员 / 禁用恢复。全部可选，至少给一项。"""

    plan: str | None = Field(default=None, pattern="^(basic|pro|max)$")
    role: str | None = Field(default=None, pattern="^(user|admin)$")
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


class AdminUserQuotaUpdateRequest(BaseModel):
    """管理员调整单个用户的当月 AI 次数上限 / 已使用次数。"""

    monthly_limit: int | None = Field(default=None, ge=0)
    used_this_month: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, max_length=300)


class AdminAuditEventInfo(BaseModel):
    """「修改历史」一条：谁在什么时候把什么从 A 改成了 B、为什么。"""

    created_at: datetime
    actor_email: str | None = None
    action: str
    before_value: str | None = None
    after_value: str | None = None
    reason: str | None = None


class AdminStats(BaseModel):
    """概览页一次取齐的计数。"""

    user_count: int
    active_invite_count: int
    pending_proposal_count: int
    pending_candidate_count: int
    active_entity_count: int
