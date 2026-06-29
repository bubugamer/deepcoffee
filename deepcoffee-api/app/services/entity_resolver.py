"""实体解析：把用户/解析得到的名字（常是别名、简写、子串）对应到系统已有实体。

两类实体两套入口（见 docs 与 plan）：
- 可穷尽实体（器具）：对照公共实体目录 `resolve_equipment`，复用 `entity_repository.resolve_entity`
  （规范名 + 全部别名，normalize_name / disambig_key 双键）。
- 不可穷尽实体（用户私有豆卡）：`resolve_user_bean` 在用户自己的豆卡里按 disambig 子串 + 活跃豆优先匹配。

设计原则（对齐产品约定）：
- 比对走规范名 + **全部别名**；命中才认，多义/模糊一律不认（返回 None，交用户手选兜底）。
- 纯函数 / 只读：不写库、不抛业务异常；解析失败只是"少认一个"，绝不打断主流程。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import PublicEntity as PublicEntityORM
from app.repositories.entities import disambig_key, entity_repository

# 器具类别（与前端 EquipmentCategory / 公共实体类型一致）。
EQUIPMENT_CATEGORIES = ("brewer", "grinder", "filter_media", "water")


async def resolve_equipment(
    session: AsyncSession, *, category: str, name: str | None
) -> PublicEntityORM | None:
    """把器具输入（可能是别名/简写/英文）解析到目录里的规范器具实体。

    命中返回公共实体（含 canonical_name / id）；目录里没有则 None（新型号 → 交 WS4 搜索确认或手输）。
    """
    if not (name or "").strip() or category not in EQUIPMENT_CATEGORIES:
        return None
    return await entity_repository.resolve_entity(session, category, name)


def _bean_attr(bean: Any, name: str) -> Any:
    return bean.get(name) if isinstance(bean, dict) else getattr(bean, name, None)


def _bean_name(bean: Any) -> str:
    return str(_bean_attr(bean, "name") or "").strip()


def _bean_id(bean: Any) -> str | None:
    return _bean_attr(bean, "bean_id") or _bean_attr(bean, "id")


def resolve_user_bean(
    parsed_name: str | None,
    *,
    beans: list[Any] | None,
    active_bean: Any = None,
) -> Any | None:
    """把解析出的豆名对应到用户已有豆卡（ORM 或 dict 皆可）。

    规则：① 有活跃豆且（解析名为空，或解析名与活跃豆名 disambig 互为子串）→ 用活跃豆；
    ② 否则在用户豆卡里按 disambig_key 完全相等 / 互为子串匹配，**唯一命中**才认；
    多义或模糊 → None（交用户手选）。返回命中的 bean（原对象），调用方取 id / name。
    """
    parsed = (parsed_name or "").strip()
    pk = disambig_key(parsed)

    if active_bean is not None:
        ak = disambig_key(_bean_name(active_bean))
        if not pk or (ak and pk and (pk in ak or ak in pk)):
            return active_bean

    if not pk or len(pk) < 2:
        return None

    exact: list[Any] = []
    fuzzy: list[Any] = []
    for bean in beans or []:
        bk = disambig_key(_bean_name(bean))
        if not bk or len(bk) < 2:
            continue
        if bk == pk:
            exact.append(bean)
        elif pk in bk or bk in pk:
            fuzzy.append(bean)
    if len(exact) == 1:
        return exact[0]
    if not exact and len(fuzzy) == 1:
        return fuzzy[0]
    return None
