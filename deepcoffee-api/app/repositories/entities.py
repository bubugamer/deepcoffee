"""公共实体库写入与读取。

提案审核通过后由这里把提案 payload **物化**成 `public_entities` + 对应分类表行（幂等，
按 (entity_type, normalized_name) 去重）。模型/用户都不能直接写这些最终表——只能经提案。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from uuid import uuid4

from sqlalchemy import Text, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import (
    CandidateFact as CandidateFactORM,
    CoffeeSource,
    EntityAlias,
    GreenBeanMerchant,
    GreenBeanProduct,
    GreenBeanProductVarietal,
    Origin,
    ProcessMethod,
    Proposal as ProposalORM,
    PublicEntity as PublicEntityORM,
    Roaster,
    RoasterProduct,
    RoasterProductVarietal,
    UserBeanCard as UserBeanCardORM,
    UserBeanCardVarietal,
    UserProfile,
    Varietal,
)
from app.schemas.entity import PublicEntity

# 提案/候选 entity_type 归一到一套规范类型。
_TYPE_ALIASES = {
    "roaster": "roaster",
    "烘焙商": "roaster",
    "coffee_source": "coffee_source",
    "producer": "coffee_source",
    "estate": "coffee_source",
    "庄园": "coffee_source",
    "处理站": "coffee_source",
    "washing_station": "coffee_source",
    "green_bean_merchant": "green_bean_merchant",
    "green_merchant": "green_bean_merchant",
    "生豆商": "green_bean_merchant",
    "importer": "green_bean_merchant",
    "进口商": "green_bean_merchant",
    "origin": "origin",
    "产地": "origin",
    "varietal": "varietal",
    "variety": "varietal",
    "品种": "varietal",
    "process": "process_method",
    "process_method": "process_method",
    "处理法": "process_method",
    "roaster_product": "roaster_product",
    "烘焙商产品": "roaster_product",
    "green_bean_product": "green_bean_product",
    "生豆商产品": "green_bean_product",
    # 器具:四类「可穷尽实体」（公共目录 + 别名）。与前端 EquipmentCategory 对齐。
    "brewer": "brewer",
    "dripper": "brewer",
    "滤杯": "brewer",
    "冲煮器具": "brewer",
    "grinder": "grinder",
    "磨豆机": "grinder",
    "filter_media": "filter_media",
    "filter": "filter_media",
    "滤纸": "filter_media",
    "过滤介质": "filter_media",
    "water": "water",
    "用水": "water",
}


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").strip().lower()
    return re.sub(r"\s+", " ", value)


def disambig_key(value: str) -> str:
    """形态归一 key：在 normalize_name 基础上再去空格与常见分隔标点，用于「大小写/空格/全半角」
    差异的自动认同（coffee buff / Coffeebuff / Coffee Buff → coffeebuff）。"""
    s = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[\s\-_/／、，,.。·|｜]+", "", s)


# 语言判定用的脚本区段（NFKC 归一后判定）。
_HAN_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")  # 汉字
_KANA_RE = re.compile(r"[぀-ヿㇰ-ㇿｦ-ﾝ]")  # 平/片假名
_LATIN_RE = re.compile(r"[A-Za-zÀ-ɏ]")  # 拉丁字母（含西欧重音）


def detect_locale(value: str) -> str | None:
    """把一个「干净的单语言名」判到 zh / ja / en，供阶段 2 按语言取显示名用。

    启发式（仅作初值，管理员可改）：含假名→ja；纯汉字→zh；纯拉丁→en。
    中英混写（如 "二氧化碳浸渍 / Carbonic Maceration"）等多脚本混合，或纯符号/数字 → None，
    即不把它当作任一语言的显示名（只继续参与匹配）。纯汉字的日文名会被判成 zh，属已知取舍。
    """
    s = unicodedata.normalize("NFKC", value or "")
    has_kana = bool(_KANA_RE.search(s))
    has_han = bool(_HAN_RE.search(s))
    has_latin = bool(_LATIN_RE.search(s))
    if has_kana and not has_latin:
        return "ja"
    if has_han and not has_kana and not has_latin:
        return "zh"
    if has_latin and not has_han and not has_kana:
        return "en"
    return None


# 主名里中英 / 多名常用分隔符；据此拆出可独立匹配的片段（如 "Captain George / 乔治队长"）。
_NAME_SPLIT_RE = re.compile(r"\s*[/／|｜、]\s*")
# 「中文（English）」括号双语名：末尾一对中/英文括号包住另一语言名。
_PAREN_BILINGUAL_RE = re.compile(r"^(.+?)\s*[（(]([^（）()]+)[）)]\s*$")


def _paren_bilingual_split(text: str) -> list[str]:
    """形如「哥斯达黎加（Costa Rica）」的括号双语名 → [外, 内]。

    仅当括号内外**各自都能干净判成中/英文、且不是同一种语言**时才拆，避免误拆「括号里是注释」
    的名字（如 "1zpresso ZP6（含 ZP6S 特调版）"，内层判不出语言 → 不拆）。
    """
    m = _PAREN_BILINGUAL_RE.match(text.strip())
    if not m:
        return []
    outer, inner = m.group(1).strip(), m.group(2).strip()
    lo, li = detect_locale(outer), detect_locale(inner)
    if outer and inner and lo and li and lo != li:
        return [outer, inner]
    return []


def alias_fragments(canonical_name: str) -> list[str]:
    """把主名拆成可独立匹配的片段（含整名本身），用于自动建别名。

    切分依据：① 斜杠 / 顿号等分隔符；② 形如「中文（English）」的括号双语名（仅内外各是干净
    且不同的语言时才拆，见 _paren_bilingual_split）。
    """
    whole = (canonical_name or "").strip()
    parts = [p.strip() for p in _NAME_SPLIT_RE.split(whole) if p.strip()]
    extra: list[str] = []
    for p in [whole, *parts]:
        extra.extend(_paren_bilingual_split(p))
    out: list[str] = []
    for p in [whole, *parts, *extra]:
        if p and p not in out:
            out.append(p)
    return out


def prefer_canonical(name: str, *, locale: str = "zh") -> tuple[str, list[str]]:
    """从可能是「中文 / English」的双语标题里,取目标语言片段作 canonical 主名,其余片段转别名。

    用于种子导入:知识库标题多写成「中文 / English」,应取中文为主名、英文等转别名,从源头杜绝
    双语主名(及「删台账后 reseed 按双语名匹配不上 → 造重复实体」的隐患)。选取规则:
    ① 优先纯目标语言(默认中文)的干净片段;② 没有则取「含该语言字符」的片段(如 "ASD 处理");
    ③ 都没有(纯英文 / 判不出)则主名保持原标题,行为不变。

    返回 (canonical, aliases):aliases 是去掉 canonical 后的其余拆分片段(含整条双语串、英文/
    别语片段),供英文/别名匹配。单一名标题 → (原名, []),无副作用。复用 alias_fragments 的切分
    (斜杠/顿号 + 括号双语),保持与全局别名逻辑一致。
    """
    whole = (name or "").strip()
    if not whole:
        return whole, []
    fragments = alias_fragments(whole)
    parts = fragments[1:]  # fragments[0] 是整条标题本身
    script_re = {"zh": _HAN_RE, "ja": _KANA_RE, "en": _LATIN_RE}.get(locale, _HAN_RE)
    chosen = (
        next((p for p in parts if detect_locale(p) == locale), None)
        or next((p for p in parts if script_re.search(p)), None)
    )
    canonical = chosen or whole
    aliases = [f for f in fragments if f != canonical]
    return canonical, aliases


def canonical_type(entity_type: str) -> str:
    return _TYPE_ALIASES.get((entity_type or "").strip().lower(), (entity_type or "").strip().lower())


class EntityRepository:
    async def get_by_type_name(
        self, session: AsyncSession, entity_type: str, name: str
    ) -> PublicEntityORM | None:
        result = await session.execute(
            select(PublicEntityORM).where(
                PublicEntityORM.entity_type == canonical_type(entity_type),
                PublicEntityORM.normalized_name == normalize_name(name),
            )
        )
        return result.scalar_one_or_none()

    async def resolve_entity(
        self, session: AsyncSession, entity_type: str, name: str
    ) -> PublicEntityORM | None:
        """统一实体匹配：先 canonical normalized_name 精确，再查别名表（normalize_name / disambig_key 两种 key）。

        形态差异（大小写/空格/全半角）经 disambig_key 自动认同；中英双名 / 译名经拆分别名命中。
        缩写 / 子串关系不在此处自动匹配（交审核「疑似并入」）。
        """
        etype = canonical_type(entity_type)
        direct = await self.get_by_type_name(session, etype, name)
        # 已合并（merged）的旧实体不再作为有效匹配——它的写法已迁成目标实体的别名，走下面别名查询命中目标。
        if direct is not None and direct.status != "merged":
            return direct
        keys = {k for k in (normalize_name(name), disambig_key(name)) if k}
        if not keys:
            return None
        result = await session.execute(
            select(PublicEntityORM)
            .join(EntityAlias, EntityAlias.entity_id == PublicEntityORM.id)
            .where(
                PublicEntityORM.entity_type == etype,
                PublicEntityORM.status != "merged",
                EntityAlias.normalized_alias.in_(keys),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def resolve_roaster_product(
        self, session: AsyncSession, *, roaster_entity_id: str | None, product_name: str | None
    ) -> PublicEntityORM | None:
        """按「烘焙商作用域」匹配 active 的 roaster_product 实体(产品名跨烘焙商会重名,必须带烘焙商约束)。

        仅返回 active 实体;烘焙商或产品名缺失则返回 None(不乱挂)。产品名按 normalize_name /
        disambig_key 两种键比对(canonical 或别名命中)。
        """
        if not roaster_entity_id or not product_name:
            return None
        keys = {k for k in (normalize_name(product_name), disambig_key(product_name)) if k}
        if not keys:
            return None
        result = await session.execute(
            select(PublicEntityORM)
            .join(RoasterProduct, RoasterProduct.entity_id == PublicEntityORM.id)
            .where(
                PublicEntityORM.entity_type == "roaster_product",
                PublicEntityORM.status == "active",
                RoasterProduct.roaster_entity_id == roaster_entity_id,
                or_(
                    PublicEntityORM.normalized_name.in_(keys),
                    PublicEntityORM.id.in_(
                        select(EntityAlias.entity_id).where(EntityAlias.normalized_alias.in_(keys))
                    ),
                ),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def register_aliases(
        self,
        session: AsyncSession,
        entity_id: str,
        canonical_name: str,
        *,
        extra: list[str] | None = None,
        source: str = "auto",
    ) -> None:
        """为实体登记匹配别名：主名 + 斜杠/顿号拆分片段 + 额外别名，各按 normalize_name 与 disambig_key 写入。

        幂等：同 (entity_id, normalized_alias) 已存在则跳过。别名表是所有匹配的统一索引（见 resolve_entity）。
        """
        names = alias_fragments(canonical_name)
        for item in extra or []:
            if isinstance(item, str) and item.strip() and item.strip() not in names:
                names.append(item.strip())
        keys: dict[str, str] = {}
        for nm in names:
            for key in (normalize_name(nm), disambig_key(nm)):
                if key:
                    keys.setdefault(key, nm)
        if not keys:
            return
        rows = await session.execute(
            select(EntityAlias.normalized_alias).where(EntityAlias.entity_id == entity_id)
        )
        have = {row[0] for row in rows.all()}
        for nkey, alias in keys.items():
            if nkey in have:
                continue
            session.add(
                EntityAlias(
                    entity_id=entity_id,
                    alias=alias,
                    normalized_alias=nkey,
                    locale=detect_locale(alias),
                    source=source,
                )
            )
        await session.flush()

    async def exists_active(self, session: AsyncSession, entity_type: str, name: str) -> bool:
        existing = await self.resolve_entity(session, entity_type, name)
        return existing is not None and existing.status == "active"

    async def find_similar(
        self, session: AsyncSession, entity_type: str, name: str, *, limit: int = 5
    ) -> list[PublicEntityORM]:
        """找「疑似已有实体」供审核人工判断（不自动合）。

        包含：① resolve_entity 精确/别名/形态命中；② canonical 的 disambig 形态与现有实体
        互为子串（覆盖缩写↔全称，如 SEY ↔ SEY Coffee）。子串只作提示，是否并入由管理员决定。
        """
        etype = canonical_type(entity_type)
        out: list[PublicEntityORM] = []
        hit = await self.resolve_entity(session, etype, name)
        if hit is not None:
            out.append(hit)
        dk = disambig_key(name)
        if dk and len(dk) >= 2:
            rows = await session.execute(
                select(PublicEntityORM).where(
                    PublicEntityORM.entity_type == etype,
                    PublicEntityORM.status == "active",
                )
            )
            seen = {e.id for e in out}
            for e in rows.scalars().all():
                if e.id in seen:
                    continue
                ek = disambig_key(e.canonical_name)
                if ek and len(ek) >= 2 and (dk in ek or ek in dk):
                    out.append(e)
                    if len(out) >= limit:
                        break
        return out[:limit]

    async def _existing_profile_id(self, session: AsyncSession, user_id: str | None) -> str | None:
        if not user_id:
            return None
        return user_id if await session.get(UserProfile, user_id) else None

    def _create_typed_row(self, etype: str, entity_id: str, payload: dict[str, Any]) -> object | None:
        """按类型建分类表行，只取 payload 里出现的已知字段。

        payload 的键既来自提案 payload，也来自 markdown 种子导入器（见
        ``entity_seed_importer``）；缺失的字段一律 None / 空容器，不编造。
        """
        if etype == "roaster":
            return Roaster(
                entity_id=entity_id,
                country=payload.get("country"),
                region=payload.get("region") or payload.get("city"),
                website_url=payload.get("website_url") or payload.get("website"),
                roaster_subtype=payload.get("roaster_subtype"),
                market=payload.get("market"),
                social_links=payload.get("social_links") or {},
                notes=payload.get("notes"),
            )
        if etype == "coffee_source":
            return CoffeeSource(
                entity_id=entity_id,
                source_type=payload.get("source_type") or payload.get("coffee_source_type") or "producer",
                country=payload.get("country"),
                region=payload.get("region"),
                subregion=payload.get("subregion"),
                altitude_m_min=payload.get("altitude_m_min"),
                altitude_m_max=payload.get("altitude_m_max"),
                notes=payload.get("notes"),
            )
        if etype == "green_bean_merchant":
            return GreenBeanMerchant(
                entity_id=entity_id,
                country=payload.get("country"),
                region=payload.get("region"),
                website_url=payload.get("website_url") or payload.get("website"),
                merchant_type=payload.get("merchant_type"),
                social_links=payload.get("social_links") or {},
                notes=payload.get("notes"),
            )
        if etype == "origin":
            return Origin(
                entity_id=entity_id,
                country=payload.get("country"),
                region=payload.get("region"),
                subregion=payload.get("subregion"),
                altitude_m_min=payload.get("altitude_m_min"),
                altitude_m_max=payload.get("altitude_m_max"),
                notes=payload.get("notes"),
            )
        if etype == "varietal":
            return Varietal(
                entity_id=entity_id,
                lineage=payload.get("lineage"),
                species=payload.get("species"),
                description=payload.get("description"),
            )
        if etype == "process_method":
            return ProcessMethod(
                entity_id=entity_id,
                process_group=payload.get("process_group"),
                description=payload.get("description"),
            )
        if etype == "roaster_product":
            return RoasterProduct(
                entity_id=entity_id,
                roaster_entity_id=payload.get("roaster_entity_id"),
                roaster_name=payload.get("roaster_name"),
                product_type=payload.get("product_type"),
                product_name=payload.get("product_name"),
                product_url=payload.get("product_url"),
                official_flavor_notes=payload.get("official_flavor_notes") or [],
                official_brew_params=payload.get("official_brew_params") or {},
            )
        if etype == "green_bean_product":
            return GreenBeanProduct(
                entity_id=entity_id,
                merchant_entity_id=payload.get("merchant_entity_id"),
                merchant_name=payload.get("merchant_name"),
                product_type=payload.get("product_type"),
                lot_name=payload.get("lot_name"),
                batch_code=payload.get("batch_code"),
                crop_year=payload.get("crop_year"),
                harvest_season=payload.get("harvest_season"),
                product_url=payload.get("product_url"),
                cupping_notes=payload.get("cupping_notes") or [],
            )
        return None

    async def upsert(
        self,
        session: AsyncSession,
        *,
        entity_type: str,
        canonical_name: str,
        payload: dict[str, Any] | None = None,
        summary: str | None = None,
        created_from: str = "proposal",
        created_by: str | None = None,
        reviewed_by: str | None = None,
    ) -> PublicEntity:
        """幂等写入公共实体（含分类表）。已存在则返回既有实体。"""
        etype = canonical_type(entity_type)
        payload = payload or {}
        existing = await self.resolve_entity(session, etype, canonical_name)
        if existing is not None:
            return PublicEntity.model_validate(existing)

        # created_by/reviewed_by 有 FK→user_profiles；提案者/管理员未必建过档（dev token 用户），
        # 不存在就置 None，避免外键冲突（provenance 仍由 created_from + 提案 proposer_id 记录）。
        created_by = await self._existing_profile_id(session, created_by)
        reviewed_by = await self._existing_profile_id(session, reviewed_by)

        entity = PublicEntityORM(
            id=f"ent_{uuid4().hex[:12]}",
            entity_type=etype,
            canonical_name=canonical_name,
            normalized_name=normalize_name(canonical_name),
            scope="public",
            status="active",
            summary=summary,
            created_from=created_from,
            created_by=created_by,
            reviewed_by=reviewed_by,
        )
        session.add(entity)
        await session.flush()
        # 自动登记匹配别名（主名拆分 + 形态 key）；payload.aliases 若有则一并登记。
        await self.register_aliases(session, entity.id, canonical_name, extra=payload.get("aliases"))
        typed = self._create_typed_row(etype, entity.id, payload)
        if typed is not None:
            session.add(typed)
            await session.flush()
        return PublicEntity.model_validate(entity)

    async def materialize_from_proposal(self, session: AsyncSession, proposal: Any) -> PublicEntity:
        payload = dict(proposal.payload or {})
        name = payload.get("name") or payload.get("canonical_name") or proposal.title
        return await self.upsert(
            session,
            entity_type=proposal.entity_type,
            canonical_name=name,
            payload=payload,
            summary=payload.get("summary"),
            created_from="proposal",
            created_by=proposal.proposer_id,
        )

    async def localized_names_for(
        self, session: AsyncSession, entity_ids: list[str]
    ) -> dict[str, dict[str, str]]:
        """批量取每个实体的 {locale: 显示名}：locale 非空的别名，每种语言取首条（按 id 稳定）。

        混合名 / 形态变体的 locale 为空，自然不会被选作显示名（见 detect_locale）。
        """
        ids = [i for i in entity_ids if i]
        if not ids:
            return {}
        rows = await session.execute(
            select(EntityAlias.entity_id, EntityAlias.locale, EntityAlias.alias)
            .where(EntityAlias.entity_id.in_(ids), EntityAlias.locale.is_not(None))
            .order_by(EntityAlias.id)
        )
        out: dict[str, dict[str, str]] = {}
        for eid, loc, alias in rows.all():
            out.setdefault(eid, {}).setdefault(loc, alias)
        return out

    async def attach_localized(
        self, session: AsyncSession, items: list[PublicEntity], locale: str | None = None
    ) -> list[PublicEntity]:
        """给一批 PublicEntity 就地填 display_name + localized_names 并返回。

        display_name 按 locale 取，取不到（或未传 locale）回退 canonical_name。
        """
        names_map = await self.localized_names_for(session, [pe.id for pe in items])
        for pe in items:
            names = names_map.get(pe.id, {})
            pe.localized_names = names
            pe.display_name = (names.get(locale) if locale else None) or pe.canonical_name
        return items

    async def list(
        self,
        session: AsyncSession,
        *,
        entity_type: str | None = None,
        status: str | None = None,
        locale: str | None = None,
    ) -> list[PublicEntity]:
        conditions = []
        if entity_type:
            conditions.append(PublicEntityORM.entity_type == canonical_type(entity_type))
        if status:
            conditions.append(PublicEntityORM.status == status)
        result = await session.execute(
            select(PublicEntityORM).where(*conditions).order_by(PublicEntityORM.created_at.desc())
        )
        items = [PublicEntity.model_validate(row) for row in result.scalars().all()]
        return await self.attach_localized(session, items, locale)

    async def count(self, session: AsyncSession, *, status: str = "active") -> int:
        result = await session.execute(
            select(func.count()).select_from(PublicEntityORM).where(PublicEntityORM.status == status)
        )
        return int(result.scalar_one())

    # ---- 阶段 4：规范主名 + 合并已有重复实体（管理员清理工具）----

    # 合并时把「指向 source 的外键」整体改指 target 的普通列（无唯一约束，直接 UPDATE）。
    _MERGE_REF_COLUMNS: list[tuple[type, list[str]]] = [
        (
            # 豆卡顶层只剩产品级实体 id；豆源级（产地/处理法/庄园/生豆商）id 在 bean_components JSONB 内，
            # 由 _merge_component_entities 单独重映射。
            UserBeanCardORM,
            ["roaster_entity_id", "roaster_product_entity_id"],
        ),
        (
            RoasterProduct,
            [
                "roaster_entity_id",
                "origin_entity_id",
                "coffee_source_entity_id",
                "green_bean_merchant_entity_id",
                "green_bean_product_entity_id",
                "process_entity_id",
            ],
        ),
        (
            GreenBeanProduct,
            ["merchant_entity_id", "coffee_source_entity_id", "origin_entity_id", "process_entity_id"],
        ),
        (CandidateFactORM, ["proposed_entity_id"]),
        (ProposalORM, ["applied_entity_id"]),
    ]

    async def _merge_aliases(self, session: AsyncSession, source_id: str, target_id: str) -> None:
        """source 的别名迁到 target；与 target 已有 normalized_alias 重复的丢弃（避免唯一冲突）。"""
        existing = await session.execute(
            select(EntityAlias.normalized_alias).where(EntityAlias.entity_id == target_id)
        )
        have = {row[0] for row in existing.all()}
        rows = await session.execute(select(EntityAlias).where(EntityAlias.entity_id == source_id))
        for alias in rows.scalars().all():
            if alias.normalized_alias in have:
                await session.delete(alias)
            else:
                alias.entity_id = target_id
                have.add(alias.normalized_alias)
        await session.flush()

    async def _merge_varietal_links(self, session: AsyncSession, source_id: str, target_id: str) -> None:
        """品种关联表 varietal_entity_id 指 source → 改 target；会撞复合主键的先删（去重）。"""
        specs = [
            (GreenBeanProductVarietal, "green_bean_product_entity_id"),
            (RoasterProductVarietal, "roaster_product_entity_id"),
            (UserBeanCardVarietal, "bean_card_id"),
        ]
        for orm, owner_col in specs:
            rows = await session.execute(select(orm).where(orm.varietal_entity_id == source_id))
            for link in rows.scalars().all():
                owner = getattr(link, owner_col)
                dup = await session.execute(
                    select(orm).where(
                        getattr(orm, owner_col) == owner, orm.varietal_entity_id == target_id
                    )
                )
                if dup.scalar_one_or_none() is not None:
                    await session.delete(link)
                else:
                    link.varietal_entity_id = target_id
            await session.flush()

    async def _merge_component_entities(self, session: AsyncSession, source_id: str, target_id: str) -> None:
        """豆源（bean_components JSONB）里缓存的实体 id 指 source → 改 target（含品种 id 列表）。"""
        id_fields = (
            "origin_entity_id",
            "process_entity_id",
            "coffee_source_entity_id",
            "green_bean_merchant_entity_id",
        )
        rows = await session.execute(
            select(UserBeanCardORM).where(cast(UserBeanCardORM.bean_components, Text).contains(source_id))
        )
        for card in rows.scalars().all():
            changed = False
            new_comps: list = []
            for comp in card.bean_components or []:
                if isinstance(comp, dict):
                    comp = dict(comp)
                    for field in id_fields:
                        if comp.get(field) == source_id:
                            comp[field] = target_id
                            changed = True
                    vids = comp.get("varietal_entity_ids")
                    if isinstance(vids, list) and source_id in vids:
                        comp["varietal_entity_ids"] = [target_id if v == source_id else v for v in vids]
                        changed = True
                new_comps.append(comp)
            if changed:
                card.bean_components = new_comps
        await session.flush()

    async def merge_entities(
        self,
        session: AsyncSession,
        *,
        source_id: str,
        target_id: str,
        reviewer_id: str | None = None,
    ) -> PublicEntity | None:
        """把 source 实体并入 target：迁移全部外键引用 + 别名，source 主名登记为 target 别名，
        source 标记 merged（不物理删，保留溯源）。返回合并后的 target。

        误合防护：仅由管理员显式触发；自合 / 实体不存在 / 类型不同一律拒绝（返回 None）。
        """
        if source_id == target_id:
            return None
        source = await session.get(PublicEntityORM, source_id)
        target = await session.get(PublicEntityORM, target_id)
        if source is None or target is None or source.entity_type != target.entity_type:
            return None
        for orm, cols in self._MERGE_REF_COLUMNS:
            for col in cols:
                await session.execute(
                    update(orm).where(getattr(orm, col) == source_id).values(**{col: target_id})
                )
        await self._merge_varietal_links(session, source_id, target_id)
        await self._merge_component_entities(session, source_id, target_id)
        await self._merge_aliases(session, source_id, target_id)
        # source 主名（及其拆分片段）登记为 target 别名，今后该写法直接命中 target。
        await self.register_aliases(session, target_id, source.canonical_name, source="merge")
        source.status = "merged"
        await session.flush()
        await session.refresh(target)
        return (await self.attach_localized(session, [PublicEntity.model_validate(target)]))[0]

    async def rename_canonical(
        self,
        session: AsyncSession,
        *,
        entity_id: str,
        new_canonical: str,
        reviewer_id: str | None = None,
    ) -> PublicEntity | None:
        """规范实体主名（把混合名 "X / 中文" 收成单一干净主名）：旧名转别名，主名与归一名改新值。

        若新名归一后与同类型其他实体撞名 → 抛 ValueError("rename_target_exists")（该走合并而非改名）。
        """
        entity = await session.get(PublicEntityORM, entity_id)
        if entity is None:
            return None
        new_norm = normalize_name(new_canonical)
        if not new_norm:
            return None
        clash = await session.execute(
            select(PublicEntityORM).where(
                PublicEntityORM.entity_type == entity.entity_type,
                PublicEntityORM.normalized_name == new_norm,
                PublicEntityORM.id != entity_id,
            )
        )
        if clash.scalar_one_or_none() is not None:
            raise ValueError("rename_target_exists")
        old_canonical = entity.canonical_name
        entity.canonical_name = new_canonical
        entity.normalized_name = new_norm
        await session.flush()
        # 旧名仍可被搜到；新名拆分片段也各登记。
        await self.register_aliases(session, entity_id, old_canonical, source="rename")
        await self.register_aliases(session, entity_id, new_canonical, source="rename")
        await session.refresh(entity)
        return (await self.attach_localized(session, [PublicEntity.model_validate(entity)]))[0]

    async def find_duplicate_groups(
        self, session: AsyncSession, *, entity_type: str | None = None, limit: int = 50
    ) -> list[tuple[str, list[PublicEntityORM]]]:
        """扫描疑似重复实体组（仅 active），供管理员人工合并：
        - "form"：disambig_key 完全相同（大小写/空格/全半角差异，多为阶段 1 前的历史遗留）。
        - "substring"：一方 disambig 是另一方子串（缩写↔全称，如 SEY ↔ SEY Coffee）。
        """
        conds = [PublicEntityORM.status == "active"]
        if entity_type:
            conds.append(PublicEntityORM.entity_type == canonical_type(entity_type))
        rows = await session.execute(select(PublicEntityORM).where(*conds))
        ents = list(rows.scalars().all())

        groups: list[tuple[str, list[PublicEntityORM]]] = []
        buckets: dict[tuple[str, str], list[PublicEntityORM]] = {}
        for e in ents:
            dk = disambig_key(e.canonical_name)
            if dk:
                buckets.setdefault((e.entity_type, dk), []).append(e)
        paired: set[str] = set()
        for members in buckets.values():
            if len(members) > 1:
                groups.append(("form", members))
                paired.update(m.id for m in members)

        by_type: dict[str, list[PublicEntityORM]] = {}
        for e in ents:
            by_type.setdefault(e.entity_type, []).append(e)
        for members in by_type.values():
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a, b = members[i], members[j]
                    if a.id in paired and b.id in paired:
                        continue
                    ka, kb = disambig_key(a.canonical_name), disambig_key(b.canonical_name)
                    if ka and kb and ka != kb and len(ka) >= 2 and len(kb) >= 2 and (ka in kb or kb in ka):
                        groups.append(("substring", [a, b]))
                        if len(groups) >= limit:
                            return groups[:limit]
        return groups[:limit]

    async def find_mixed_names(
        self, session: AsyncSession, *, entity_type: str | None = None, limit: int = 100
    ) -> list[PublicEntityORM]:
        """canonical 仍是混合主名（含 / ｜ 、 等分隔、可拆成多片段）的 active 实体，建议规范成单一主名。"""
        conds = [PublicEntityORM.status == "active"]
        if entity_type:
            conds.append(PublicEntityORM.entity_type == canonical_type(entity_type))
        rows = await session.execute(select(PublicEntityORM).where(*conds))
        out = [e for e in rows.scalars().all() if len(alias_fragments(e.canonical_name)) > 1]
        return out[:limit]


entity_repository = EntityRepository()
