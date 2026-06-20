from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str | None] = mapped_column(String, unique=True)
    display_name: Mapped[str | None] = mapped_column(String)
    plan: Mapped[str] = mapped_column(String, default="basic", server_default="basic", nullable=False)
    # 管理员身份持久化在 DB（user / admin）。环境变量 DEEPCOFFEE_ADMIN_USER_IDS 仍可作兜底名单。
    # 注意：user_profiles 在 Supabase 已存在，create_all 不会补列，上线前需手跑 ALTER（见 migrations/004、005）。
    role: Mapped[str] = mapped_column(String, default="user", server_default="user", nullable=False)
    # 账号状态（active / disabled）。disabled 由管理员设置，业务接口与 /me 一律 403 account_disabled。
    status: Mapped[str] = mapped_column(String, default="active", server_default="active", nullable=False)
    timezone: Mapped[str] = mapped_column(String, default="Asia/Shanghai", server_default="Asia/Shanghai", nullable=False)
    unit_system: Mapped[str] = mapped_column(String, default="metric", server_default="metric", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class InviteCode(Base):
    __tablename__ = "invite_codes"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="active", server_default="active", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    used_by: Mapped[str | None] = mapped_column(String, ForeignKey("user_profiles.id"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PublicEntity(Base):
    __tablename__ = "public_entities"
    __table_args__ = (UniqueConstraint("entity_type", "normalized_name", name="public_entities_type_name_uq"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(String, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String, default="public", server_default="public", nullable=False)
    status: Mapped[str] = mapped_column(String, default="active", server_default="active", nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    created_from: Mapped[str] = mapped_column(String, default="admin", server_default="admin", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("user_profiles.id", ondelete="SET NULL"))
    reviewed_by: Mapped[str | None] = mapped_column(String, ForeignKey("user_profiles.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Roaster(Base):
    __tablename__ = "roasters"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="CASCADE"), primary_key=True
    )
    country: Mapped[str | None] = mapped_column(String)
    region: Mapped[str | None] = mapped_column(String)
    website_url: Mapped[str | None] = mapped_column(String)
    roaster_subtype: Mapped[str | None] = mapped_column(String)
    market: Mapped[str | None] = mapped_column(String)
    social_links: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class CoffeeSource(Base):
    """Producer / estate / washing station. Separate from green bean merchants."""

    __tablename__ = "coffee_sources"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="CASCADE"), primary_key=True
    )
    source_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    country: Mapped[str | None] = mapped_column(String)
    region: Mapped[str | None] = mapped_column(String)
    subregion: Mapped[str | None] = mapped_column(String)
    altitude_m_min: Mapped[int | None] = mapped_column(Integer)
    altitude_m_max: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)


class GreenBeanMerchant(Base):
    __tablename__ = "green_bean_merchants"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="CASCADE"), primary_key=True
    )
    country: Mapped[str | None] = mapped_column(String)
    region: Mapped[str | None] = mapped_column(String)
    website_url: Mapped[str | None] = mapped_column(String)
    merchant_type: Mapped[str | None] = mapped_column(String)
    social_links: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class Origin(Base):
    __tablename__ = "origins"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="CASCADE"), primary_key=True
    )
    country: Mapped[str | None] = mapped_column(String)
    region: Mapped[str | None] = mapped_column(String)
    subregion: Mapped[str | None] = mapped_column(String)
    altitude_m_min: Mapped[int | None] = mapped_column(Integer)
    altitude_m_max: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)


class Varietal(Base):
    __tablename__ = "varietals"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="CASCADE"), primary_key=True
    )
    lineage: Mapped[str | None] = mapped_column(String)
    species: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)


class ProcessMethod(Base):
    __tablename__ = "process_methods"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="CASCADE"), primary_key=True
    )
    process_group: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)


class GreenBeanProduct(Base):
    __tablename__ = "green_bean_products"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="CASCADE"), primary_key=True
    )
    merchant_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    coffee_source_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    origin_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    process_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    merchant_name: Mapped[str | None] = mapped_column(String)
    product_type: Mapped[str | None] = mapped_column(String)
    lot_name: Mapped[str | None] = mapped_column(String)
    batch_code: Mapped[str | None] = mapped_column(String)
    crop_year: Mapped[str | None] = mapped_column(String)
    harvest_season: Mapped[str | None] = mapped_column(String)
    product_url: Mapped[str | None] = mapped_column(String)
    cupping_notes: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)


class RoasterProduct(Base):
    __tablename__ = "roaster_products"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="CASCADE"), primary_key=True
    )
    roaster_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    origin_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    coffee_source_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    green_bean_merchant_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    green_bean_product_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    process_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    roaster_name: Mapped[str | None] = mapped_column(String)
    product_type: Mapped[str | None] = mapped_column(String)
    product_name: Mapped[str | None] = mapped_column(String)
    product_url: Mapped[str | None] = mapped_column(String)
    official_flavor_notes: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    flavor_profile: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    official_brew_params: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)


class GreenBeanProductVarietal(Base):
    __tablename__ = "green_bean_product_varietals"

    green_bean_product_entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="CASCADE"), primary_key=True
    )
    varietal_entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="CASCADE"), primary_key=True
    )


class RoasterProductVarietal(Base):
    __tablename__ = "roaster_product_varietals"

    roaster_product_entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="CASCADE"), primary_key=True
    )
    varietal_entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="CASCADE"), primary_key=True
    )


class EntityAlias(Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (UniqueConstraint("entity_id", "normalized_alias", name="entity_aliases_entity_alias_uq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String, ForeignKey("public_entities.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String, nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String, nullable=False, index=True)
    locale: Mapped[str | None] = mapped_column(String)
    source: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EntitySource(Base):
    __tablename__ = "entity_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String, ForeignKey("public_entities.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String)
    source_title: Mapped[str | None] = mapped_column(String)
    source_text: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("user_profiles.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserBeanCard(Base):
    __tablename__ = "user_bean_cards"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String, default="private", server_default="private", nullable=False)
    status: Mapped[str] = mapped_column(String, default="active", server_default="active", nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String, default="text", server_default="text", nullable=False)
    raw_input: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String, nullable=False)

    roaster_name: Mapped[str | None] = mapped_column(String)
    roaster_product_name: Mapped[str | None] = mapped_column(String)
    coffee_source_name: Mapped[str | None] = mapped_column(String)
    green_bean_merchant_name: Mapped[str | None] = mapped_column(String)
    green_bean_product_name: Mapped[str | None] = mapped_column(String)
    origin_name: Mapped[str | None] = mapped_column(String)
    process_name: Mapped[str | None] = mapped_column(String)
    varietal_names: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)

    roaster_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    roaster_product_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    coffee_source_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    green_bean_merchant_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    green_bean_product_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    origin_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    process_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )

    flavor: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    rating: Mapped[dict | None] = mapped_column(JSONB)
    private_notes: Mapped[str | None] = mapped_column(Text)
    recommended_record_id: Mapped[str | None] = mapped_column(String)
    trace_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserBeanCardVarietal(Base):
    __tablename__ = "user_bean_card_varietals"

    bean_card_id: Mapped[str] = mapped_column(
        String, ForeignKey("user_bean_cards.id", ondelete="CASCADE"), primary_key=True
    )
    varietal_entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="CASCADE"), primary_key=True
    )


class BrewRecord(Base):
    __tablename__ = "brew_records"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    bean_card_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("user_bean_cards.id", ondelete="SET NULL"), index=True
    )
    record_type: Mapped[str] = mapped_column(String, default="user", server_default="user", nullable=False, index=True)
    is_user_visible: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    source_type: Mapped[str] = mapped_column(String, default="text", server_default="text", nullable=False)
    raw_input: Mapped[str | None] = mapped_column(Text)

    bean_name: Mapped[str | None] = mapped_column(String)
    origin: Mapped[str | None] = mapped_column(String)
    roaster: Mapped[str | None] = mapped_column(String)
    process: Mapped[str | None] = mapped_column(String)
    varietal: Mapped[str | None] = mapped_column(String)
    brew_method: Mapped[str | None] = mapped_column(String)
    device: Mapped[str | None] = mapped_column(String)
    grinder: Mapped[str | None] = mapped_column(String)
    grind_setting: Mapped[str | None] = mapped_column(String)
    filter_media: Mapped[str | None] = mapped_column(String)
    water: Mapped[str | None] = mapped_column(String)
    dose_g: Mapped[float | None] = mapped_column(Float)
    water_ml: Mapped[float | None] = mapped_column(Float)
    water_temp_c: Mapped[float | None] = mapped_column(Float)
    ratio: Mapped[str | None] = mapped_column(String)
    ratio_value: Mapped[float | None] = mapped_column(Float)
    brew_time: Mapped[str | None] = mapped_column(String)
    brew_time_seconds: Mapped[int | None] = mapped_column(Integer)

    brew_steps: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    evaluation: Mapped[dict | None] = mapped_column(JSONB)
    brew_score: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    recap: Mapped[str | None] = mapped_column(Text)
    suggestions: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Proposal(Base):
    __tablename__ = "public_entity_proposals"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    source_input: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String)
    proposer_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending", server_default="pending", nullable=False, index=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    applied_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    applied_markdown_path: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    audit: Mapped[list["ProposalAuditEvent"]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
        order_by="ProposalAuditEvent.created_at",
        lazy="selectin",
    )


class ProposalAuditEvent(Base):
    __tablename__ = "proposal_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[str] = mapped_column(
        String, ForeignKey("public_entity_proposals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    proposal: Mapped["Proposal"] = relationship(back_populates="audit")


class CandidateFact(Base):
    __tablename__ = "candidate_facts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    fact_type: Mapped[str | None] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    source_scope: Mapped[str] = mapped_column(String, default="private", server_default="private", nullable=False)
    source_table: Mapped[str | None] = mapped_column(String)
    source_record_id: Mapped[str | None] = mapped_column(String)
    source_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("user_profiles.id", ondelete="SET NULL"))
    source_input: Mapped[str | None] = mapped_column(Text)
    proposed_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entities.id", ondelete="SET NULL"), index=True
    )
    proposal_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("public_entity_proposals.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(
        String, default="pending_review", server_default="pending_review", nullable=False, index=True
    )
    reviewer_id: Mapped[str | None] = mapped_column(String, ForeignKey("user_profiles.id", ondelete="SET NULL"))
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trace_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KnowledgeSyncRecord(Base):
    __tablename__ = "knowledge_sync_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String, ForeignKey("public_entities.id", ondelete="CASCADE"), index=True)
    sync_target: Mapped[str] = mapped_column(String, nullable=False)
    markdown_path: Mapped[str] = mapped_column(String, nullable=False, index=True)
    content_hash: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending", server_default="pending", nullable=False, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AiUsageEvent(Base):
    __tablename__ = "ai_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserAiQuotaSetting(Base):
    __tablename__ = "user_ai_quota_settings"

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("user_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    # null means "use plan default"; otherwise this exact monthly cap overrides the plan.
    monthly_limit: Mapped[int | None] = mapped_column(Integer)
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("user_profiles.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AiUsageAdjustment(Base):
    __tablename__ = "ai_usage_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[str | None] = mapped_column(String, ForeignKey("user_profiles.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AdminAuditEvent(Base):
    """管理员对用户的修改审计（套餐/角色/状态/额度）。一次字段变更一条，按时间倒序展示。"""

    __tablename__ = "admin_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[str | None] = mapped_column(String, ForeignKey("user_profiles.id", ondelete="SET NULL"))
    # plan_change / role_change / status_change / quota_limit_change / usage_adjust
    action: Mapped[str] = mapped_column(String, nullable=False)
    before_value: Mapped[str | None] = mapped_column(String)
    after_value: Mapped[str | None] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserEquipmentProfile(Base):
    """用户器具资料（冲煮方式 / 滤杯 / 磨豆机 / 过滤介质 / 水）。可多套。

    bean_recommend_params 多轮闭环在 completed 时保存（见 docs/deepcoffee-ai-prompts.md §5）；
    下次建议直接带上，不必再问。
    """

    __tablename__ = "user_equipment_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 冲煮方式（下拉枚举：滤杯冲煮 / 意式 / 法压壶 / 爱乐压 / 浸泡式 / 摩卡壶 / 虹吸壶 / 冷萃），默认滤杯冲煮。
    brew_method: Mapped[str | None] = mapped_column(String)
    # 滤杯 / 冲煮器具（自由文本，如 V60、Kalita、Origami）；recommend 闭环用它当 device。
    dripper: Mapped[str | None] = mapped_column(String)
    grinder: Mapped[str | None] = mapped_column(String)
    filter_media: Mapped[str | None] = mapped_column(String)
    water: Mapped[str | None] = mapped_column(String)
    label: Mapped[str | None] = mapped_column(String)
    # 默认器具套：生成建议时未指定则用它；单默认不变量由 equipment_repository.set_default 维护。
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserEquipmentItem(Base):
    """用户单件器具库存。替代 user_equipment_profiles 作为业务读写主表。"""

    __tablename__ = "user_equipment_items"
    __table_args__ = (
        UniqueConstraint("user_id", "category", "normalized_name", name="user_equipment_items_user_category_name_uq"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CoffeaSession(Base):
    """Coffea 统一会话状态（coffea_dispatch）。一个 session_id 一行，维护 active 实体与近期消息。

    见 docs/deepcoffee-ai-prompts.md §0「会话与多轮状态」：全局只有一个 session_id 命名空间。
    """

    __tablename__ = "coffea_sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # active_bean_id / active_recipe_id / active_brew_id / active_equipment_id 及用户偏好等。
    state: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    # 最近若干轮消息（{"role", "content"}），按预算裁剪；只存当前用户自己的内容。
    recent_messages: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    # 主题式长期摘要（L2）：list[{topic, content, time_hint}]，超窗口的老对话增量并入。
    summary: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserMemory(Base):
    """用户长期记忆条目（L3 画像）：从对话 / 冲煮记录沉淀的稳定偏好与事实，跨会话注入。

    条目化便于单条增删改与溯源；用户可在「我的口味档案」查看 / 纠正 / 删除。
    kind: taste（口味）/ equipment（器具习惯）/ habit（冲煮习惯）/ goal（目标）/ fact（其他事实）。
    """

    __tablename__ = "user_memories"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.6, server_default="0.6", nullable=False)
    # 来源：dialog / brew_record；source_ref 存对应轮次时间戳或记录 id，便于溯源。
    source: Mapped[str | None] = mapped_column(String)
    source_ref: Mapped[str | None] = mapped_column(String)
    # active / dismissed：用户删除即置 dismissed（不物理删，避免抽取重复加回同一条）。
    status: Mapped[str] = mapped_column(String, default="active", server_default="active", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
