"""Markdown 实体种子 → 公共实体库 的结构化导入器（冷启动填充）。

把知识库里 `knowledge_role: entity_seed` 的支撑页（烘焙商 / 庄园 / 生豆商 / 品种 /
处理法 / 产区 / 产品…）按 frontmatter 结构化灌进 `public_entities` + 分类表 +
`entity_aliases` + `entity_sources`。设计要点（均为已商定决策）：

1. 准入：``visibility=support`` 且 ``knowledge_role=entity_seed`` 且 ``entity_type``
   在白名单内，三者全满足才纳入。
2. 稳定键 / 幂等：用 ``knowledge_sync_records``（``markdown_path`` + ``content_hash``）
   记"哪个文件 ↔ 哪条实体"。改名原地更新、内容未变跳过——可反复跑。
3. 归属权：种子只写/更新 ``created_from='markdown'`` 且未被审核（``reviewed_by IS NULL``）
   的实体；一旦被提案 / 人工接管，退为只读、永不覆盖。
4. 同批连外键：同批内精确名匹配就把 ``merchant_entity_id`` / ``roaster_entity_id`` 连上；
   连不上才退回只存 ``merchant_name`` / ``roaster_name`` 字符串。
5. 安全闸：``dry_run`` 只算计划、不落库；CLI 默认先 dry-run。
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import (
    EntityAlias,
    EntitySource,
    KnowledgeSyncRecord,
    PublicEntity as PublicEntityORM,
)
from app.repositories.entities import EntityRepository, canonical_type, detect_locale, normalize_name
from app.services.knowledge_service import (
    _meta_date,
    _meta_list,
    _meta_str,
    extract_summary,
    extract_title,
    split_frontmatter,
)

SYNC_TARGET = "public_entity"
ALIAS_SOURCE = "markdown_seed"

# 准入白名单（已归一的规范类型）。green_merchant 在归一阶段映射为 green_bean_merchant。
SEED_ENTITY_TYPES = frozenset(
    {
        "roaster",
        "roaster_product",
        "coffee_source",
        "green_bean_merchant",
        "green_bean_product",
        "origin",
        "varietal",
        "process_method",
    }
)


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _as_dict(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


@dataclass
class SeedPage:
    path: str  # 相对知识库根的 posix 路径，作稳定键
    entity_type: str  # 已归一
    canonical_name: str
    normalized_name: str
    status: str
    scope: str
    summary: str | None
    aliases: list[str]
    sources: list[dict]
    payload: dict
    content_hash: str
    merchant_name: str | None = None  # green_bean_product 用
    roaster_name: str | None = None  # roaster_product 用


@dataclass
class SeedReport:
    dry_run: bool
    created: list[tuple[str, str, str]] = field(default_factory=list)  # (path, type, name)
    updated: list[tuple[str, str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str, str]] = field(default_factory=list)  # (path, name, reason)
    linked: list[tuple[str, str, str]] = field(default_factory=list)  # (path, link_type, target)
    name_only: list[tuple[str, str, str]] = field(default_factory=list)  # (path, link_type, name)
    by_type: Counter = field(default_factory=Counter)

    def render(self) -> str:
        mode = "DRY-RUN（不写库）" if self.dry_run else "已写入"
        lines = [
            f"=== 实体种子导入报告 · {mode} ===",
            f"新建 {len(self.created)} · 更新 {len(self.updated)} · 跳过 {len(self.skipped)}"
            f" · 连外键 {len(self.linked)} · 仅存名 {len(self.name_only)}",
            "",
            "按类型（新建+更新）：" + (
                ", ".join(f"{t}×{n}" for t, n in sorted(self.by_type.items())) or "（无）"
            ),
        ]
        if self.created:
            lines += ["", "新建："]
            lines += [f"  + [{t}] {name}  ({path})" for path, t, name in self.created]
        if self.updated:
            lines += ["", "更新："]
            lines += [f"  ~ [{t}] {name}  ({path})" for path, t, name in self.updated]
        if self.linked:
            lines += ["", "同批连外键："]
            lines += [f"  → {path}  --{lt}-->  {target}" for path, lt, target in self.linked]
        if self.name_only:
            lines += ["", "未匹配（仅存名字）："]
            lines += [f"  · {path}  {lt}={name}" for path, lt, name in self.name_only]
        if self.skipped:
            lines += ["", "跳过："]
            lines += [f"  - {name}  ({reason})  [{path}]" for path, name, reason in self.skipped]
        return "\n".join(lines)


class EntitySeedImporter:
    def __init__(self, knowledge_dir: Path, repo: EntityRepository | None = None) -> None:
        self.knowledge_dir = Path(knowledge_dir)
        self.repo = repo or EntityRepository()

    # ---- 扫描 / 解析 ----------------------------------------------------

    def scan(self) -> list[SeedPage]:
        if not self.knowledge_dir.exists():
            raise FileNotFoundError(f"knowledge_dir not found: {self.knowledge_dir}")
        seeds: list[SeedPage] = []
        for path in sorted(self.knowledge_dir.rglob("*.md")):
            rel = path.relative_to(self.knowledge_dir)
            if rel.name == "index.md" or "stylesheets" in rel.parts:
                continue
            raw = path.read_text(encoding="utf-8")
            meta, body = split_frontmatter(raw)
            if not self._is_seed(meta):
                continue
            seed = self._build_seed(rel, meta, body, raw)
            if seed is not None:
                seeds.append(seed)
        return seeds

    def _is_seed(self, meta: dict) -> bool:
        visibility = (_meta_str(meta.get("visibility")) or "public").lower()
        role = (_meta_str(meta.get("knowledge_role")) or "").lower()
        etype = canonical_type(_meta_str(meta.get("entity_type")) or "")
        return visibility == "support" and role == "entity_seed" and etype in SEED_ENTITY_TYPES

    def _build_seed(self, rel: Path, meta: dict, body: str, raw: str) -> SeedPage | None:
        etype = canonical_type(_meta_str(meta.get("entity_type")) or "")
        title = _meta_str(meta.get("title")) or extract_title(body, rel.with_suffix("").name)
        if not title:
            return None
        summary = extract_summary(body) or None
        merchant_name = _meta_str(meta.get("merchant"))
        roaster_name = _meta_str(meta.get("roaster"))
        return SeedPage(
            path=rel.as_posix(),
            entity_type=etype,
            canonical_name=title,
            normalized_name=normalize_name(title),
            status=_meta_str(meta.get("status")) or "active",
            scope=_meta_str(meta.get("scope")) or "public",
            summary=summary,
            aliases=_meta_list(meta.get("aliases")),
            sources=self._build_sources(meta.get("sources")),
            payload=self._build_payload(etype, meta, title, merchant_name, roaster_name),
            content_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            merchant_name=merchant_name,
            roaster_name=roaster_name,
        )

    def _build_sources(self, value: object) -> list[dict]:
        if not isinstance(value, list):
            return []
        out: list[dict] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "source_type": _meta_str(item.get("type")) or "unknown",
                    "source_url": _meta_str(item.get("url")),
                    "source_title": _meta_str(item.get("title")),
                    "source_text": _meta_str(item.get("path")),
                    "captured_at": _meta_date(item.get("accessed")),
                }
            )
        return out

    def _build_payload(
        self, etype: str, meta: dict, title: str, merchant_name: str | None, roaster_name: str | None
    ) -> dict:
        common_geo = {
            "country": _meta_str(meta.get("country")),
            "region": _meta_str(meta.get("region")),
            "subregion": _meta_str(meta.get("subregion")),
            "altitude_m_min": _as_int(meta.get("altitude_m_min")),
            "altitude_m_max": _as_int(meta.get("altitude_m_max")),
            "notes": _meta_str(meta.get("notes")),
        }
        if etype == "roaster":
            return {
                "country": _meta_str(meta.get("country")),
                "region": _meta_str(meta.get("region")) or _meta_str(meta.get("city")),
                "website_url": _meta_str(meta.get("website_url")) or _meta_str(meta.get("website")),
                "roaster_subtype": _meta_str(meta.get("roaster_subtype")),
                "market": _meta_str(meta.get("market")),
                "social_links": _as_dict(meta.get("social_links")),
                "notes": _meta_str(meta.get("notes")),
            }
        if etype == "green_bean_merchant":
            return {
                "country": _meta_str(meta.get("country")),
                "region": _meta_str(meta.get("region")),
                "website_url": _meta_str(meta.get("website_url")) or _meta_str(meta.get("website")),
                "merchant_type": _meta_str(meta.get("merchant_type")),
                "social_links": _as_dict(meta.get("social_links")),
                "notes": _meta_str(meta.get("notes")),
            }
        if etype == "coffee_source":
            return {
                "source_type": _meta_str(meta.get("coffee_source_type")) or _meta_str(meta.get("source_type")),
                **common_geo,
            }
        if etype == "origin":
            return common_geo
        if etype == "varietal":
            return {
                "lineage": _meta_str(meta.get("lineage")),
                "species": _meta_str(meta.get("species")),
                "description": _meta_str(meta.get("description")),
            }
        if etype == "process_method":
            return {
                "process_group": _meta_str(meta.get("process_group")),
                "description": _meta_str(meta.get("description")),
            }
        if etype == "green_bean_product":
            return {
                "merchant_name": merchant_name,
                "product_type": _meta_str(meta.get("product_type")),
                "lot_name": _meta_str(meta.get("lot_name")),
                "batch_code": _meta_str(meta.get("batch_code")),
                "crop_year": _meta_str(meta.get("crop_year")),
                "harvest_season": _meta_str(meta.get("harvest_season")),
                "product_url": _meta_str(meta.get("product_url")),
                "cupping_notes": _meta_list(meta.get("cupping_notes")),
            }
        if etype == "roaster_product":
            return {
                "roaster_name": roaster_name,
                "product_type": _meta_str(meta.get("product_type")),
                "product_name": title,
                "product_url": _meta_str(meta.get("product_url")),
                "official_flavor_notes": _meta_list(meta.get("official_flavor_notes")),
                "official_brew_params": _as_dict(meta.get("official_brew_params")),
            }
        return {}

    # ---- 运行 -----------------------------------------------------------

    async def run(self, session: AsyncSession, *, dry_run: bool = False) -> SeedReport:
        seeds = self.scan()
        report = SeedReport(dry_run=dry_run)
        records = await self._load_sync_records(session, [s.path for s in seeds])

        # 同批内 merchant / roaster 名集合，用于外键连接预测与解析。
        batch_merchant = {s.normalized_name for s in seeds if s.entity_type == "green_bean_merchant"}
        batch_roaster = {s.normalized_name for s in seeds if s.entity_type == "roaster"}

        for seed in seeds:
            action, entity_id, reason = await self._decide(session, seed, records.get(seed.path))
            if action == "skip":
                report.skipped.append((seed.path, seed.canonical_name, reason))
                self._record_link_prediction(report, seed, batch_merchant, batch_roaster)
                continue
            if not dry_run:
                entity_id = await self._apply(session, seed, action, entity_id)
            if action == "create":
                report.created.append((seed.path, seed.entity_type, seed.canonical_name))
            else:
                report.updated.append((seed.path, seed.entity_type, seed.canonical_name))
            report.by_type[seed.entity_type] += 1
            self._record_link_prediction(report, seed, batch_merchant, batch_roaster)

        if not dry_run:
            await self._link_products(session, seeds, records)
            await session.flush()
        return report

    def _record_link_prediction(
        self, report: SeedReport, seed: SeedPage, batch_merchant: set[str], batch_roaster: set[str]
    ) -> None:
        if seed.entity_type == "green_bean_product" and seed.merchant_name:
            target = normalize_name(seed.merchant_name)
            bucket = report.linked if target in batch_merchant else report.name_only
            bucket.append((seed.path, "merchant", seed.merchant_name))
        elif seed.entity_type == "roaster_product" and seed.roaster_name:
            target = normalize_name(seed.roaster_name)
            bucket = report.linked if target in batch_roaster else report.name_only
            bucket.append((seed.path, "roaster", seed.roaster_name))

    async def _load_sync_records(
        self, session: AsyncSession, paths: list[str]
    ) -> dict[str, KnowledgeSyncRecord]:
        if not paths:
            return {}
        rows = (
            await session.execute(
                select(KnowledgeSyncRecord).where(
                    KnowledgeSyncRecord.sync_target == SYNC_TARGET,
                    KnowledgeSyncRecord.markdown_path.in_(paths),
                )
            )
        ).scalars().all()
        return {r.markdown_path: r for r in rows}

    @staticmethod
    def _is_markdown_owned(entity: PublicEntityORM) -> bool:
        return entity.created_from == "markdown" and entity.reviewed_by is None

    async def _decide(
        self, session: AsyncSession, seed: SeedPage, record: KnowledgeSyncRecord | None
    ) -> tuple[str, str | None, str]:
        if record is not None:
            entity = await session.get(PublicEntityORM, record.entity_id)
            if entity is None:
                return "create", None, "台账指向的实体已不存在，重建"
            if not self._is_markdown_owned(entity):
                return "skip", entity.id, "已被提案/人工接管，只读不覆盖"
            if record.content_hash == seed.content_hash:
                return "skip", entity.id, "内容未变"
            return "update", entity.id, "内容已变，更新"
        existing = await self.repo.get_by_type_name(session, seed.entity_type, seed.canonical_name)
        if existing is not None:
            if self._is_markdown_owned(existing):
                return "update", existing.id, "按名匹配到既有种子实体，接管台账"
            return "skip", existing.id, "同名实体已被非种子来源占用"
        return "create", None, "新建"

    async def _apply(
        self, session: AsyncSession, seed: SeedPage, action: str, entity_id: str | None
    ) -> str:
        if action == "create" or entity_id is None:
            entity = PublicEntityORM(
                id=f"ent_{uuid4().hex[:12]}",
                entity_type=seed.entity_type,
                canonical_name=seed.canonical_name,
                normalized_name=seed.normalized_name,
                scope=seed.scope,
                status=seed.status,
                summary=seed.summary,
                created_from="markdown",
            )
            session.add(entity)
            await session.flush()
            entity_id = entity.id
        else:
            entity = await session.get(PublicEntityORM, entity_id)
            entity.canonical_name = seed.canonical_name
            entity.normalized_name = seed.normalized_name
            entity.scope = seed.scope
            entity.status = seed.status
            entity.summary = seed.summary
            # 清掉旧的分类表行 / 种子别名 / 来源，整篇按 frontmatter 重铺（实体归种子所有）。
            await session.execute(delete(EntityAlias).where(EntityAlias.entity_id == entity_id, EntityAlias.source == ALIAS_SOURCE))
            await session.execute(delete(EntitySource).where(EntitySource.entity_id == entity_id))
            await self._delete_typed_row(session, seed.entity_type, entity_id)
            await session.flush()

        typed = self.repo._create_typed_row(seed.entity_type, entity_id, seed.payload)
        if typed is not None:
            session.add(typed)
        for alias in seed.aliases:
            session.add(
                EntityAlias(
                    entity_id=entity_id,
                    alias=alias,
                    normalized_alias=normalize_name(alias),
                    locale=detect_locale(alias),
                    source=ALIAS_SOURCE,
                )
            )
        for src in seed.sources:
            session.add(EntitySource(entity_id=entity_id, **src))
        await self._upsert_sync_record(session, seed, entity_id)
        await session.flush()
        return entity_id

    async def _delete_typed_row(self, session: AsyncSession, etype: str, entity_id: str) -> None:
        sample = self.repo._create_typed_row(etype, entity_id, {})
        if sample is None:
            return
        await session.execute(delete(type(sample)).where(type(sample).entity_id == entity_id))

    async def _upsert_sync_record(
        self, session: AsyncSession, seed: SeedPage, entity_id: str
    ) -> None:
        existing = (
            await session.execute(
                select(KnowledgeSyncRecord).where(
                    KnowledgeSyncRecord.sync_target == SYNC_TARGET,
                    KnowledgeSyncRecord.markdown_path == seed.path,
                )
            )
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if existing is None:
            session.add(
                KnowledgeSyncRecord(
                    entity_id=entity_id,
                    sync_target=SYNC_TARGET,
                    markdown_path=seed.path,
                    content_hash=seed.content_hash,
                    status="synced",
                    last_synced_at=now,
                )
            )
        else:
            existing.entity_id = entity_id
            existing.content_hash = seed.content_hash
            existing.status = "synced"
            existing.last_synced_at = now

    async def _link_products(
        self, session: AsyncSession, seeds: list[SeedPage], records: dict[str, KnowledgeSyncRecord]
    ) -> None:
        """第二趟：把产品的 merchant/roaster 名解析成外键（同批已 flush，可查到）。"""
        from app.models.tables import GreenBeanProduct, RoasterProduct

        for seed in seeds:
            if seed.entity_type == "green_bean_product" and seed.merchant_name:
                merchant = await self.repo.get_by_type_name(
                    session, "green_bean_merchant", seed.merchant_name
                )
                if merchant is None:
                    continue
                eid = await self._entity_id_for_path(session, seed.path)
                row = await session.get(GreenBeanProduct, eid) if eid else None
                if row is not None:
                    row.merchant_entity_id = merchant.id
            elif seed.entity_type == "roaster_product" and seed.roaster_name:
                roaster = await self.repo.get_by_type_name(session, "roaster", seed.roaster_name)
                if roaster is None:
                    continue
                eid = await self._entity_id_for_path(session, seed.path)
                row = await session.get(RoasterProduct, eid) if eid else None
                if row is not None:
                    row.roaster_entity_id = roaster.id

    async def _entity_id_for_path(self, session: AsyncSession, path: str) -> str | None:
        return (
            await session.execute(
                select(KnowledgeSyncRecord.entity_id).where(
                    KnowledgeSyncRecord.sync_target == SYNC_TARGET,
                    KnowledgeSyncRecord.markdown_path == path,
                )
            )
        ).scalar_one_or_none()
