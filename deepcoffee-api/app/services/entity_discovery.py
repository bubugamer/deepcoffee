"""新实体发现（不可穷尽 / 目录未覆盖的处理）：对未命中器具目录的输入，用大模型给出
规范名 + 别名，落成**候选（candidate）**进管理员审核链路；审核通过后入目录，今后即可命中。

设计（对齐 plan 的保守取舍）：
- 只产候选，**不自动建 active 公共实体**——避免未经审核的搜索结果污染策展好的目录。
- 去重：已是 active 实体 / 已有未关闭候选 → 跳过；若大模型给的规范名其实已在目录（别名命中），
  则把用户的原始写法登记为该实体别名（今后直接命中），不重复建候选。
- 失败 / 低置信 / 判定非真实器具 → 不落候选（用户当轮仍走手输兜底，互不影响）。
- 跑在后台任务里（独立 session），绝不阻塞对话响应。

发现用提示词为本服务私有常量（不进 app/prompts 的逐字校验清单，便于该新功能迭代）。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker
from app.repositories.candidates import candidate_repository
from app.repositories.entities import entity_repository
from app.services.entity_resolver import EQUIPMENT_CATEGORIES, resolve_equipment
from app.services.model_gateway import ModelGateway, model_gateway
from app.services.model_json import ModelJSONError, chat_json

logger = logging.getLogger(__name__)

_CATEGORY_LABEL = {
    "brewer": "冲煮器具（滤杯 / 手冲壶 / 法压壶 / 爱乐压 / 聪明杯等）",
    "grinder": "磨豆机",
    "filter_media": "过滤介质（滤纸 / 金属滤网等）",
    "water": "冲煮用水",
}

_DISCOVER_SYSTEM = """你是 DeepCoffee 的器具目录助手。给定一个用户输入的器具名字（可能是简写、缩写、英文或中英混写），判断它对应市面上哪一件真实存在的器具，并给出规范名与尽量全的别名。

只输出一个合法 JSON 对象，不要输出解释、不要 markdown、不要代码块。JSON 必须且只能包含这些键：
- is_real_equipment: 布尔值；能确定它是一件真实存在的具体器具才为 true，看不准 / 编不出 / 不是器具一律 false
- canonical_name: 字符串，规范名（品牌 + 型号，优先简体中文通行叫法；没有中文名就用通行英文名）
- aliases: 字符串数组，尽量覆盖该器具的简写、缩写、英文名、中文名、常见别名（可含用户的原始输入）
- confidence: 0 到 1 的数字

规则：
1. 不要编造不存在的型号或品牌；拿不准就 is_real_equipment=false。
2. canonical_name 用具体型号粒度（如「1Zpresso ZP6S」「Hario V60」），不要用宽泛品类。
3. aliases 尽量全但都要是真实别名，不要把无关词塞进去。"""


async def discover_equipment(
    session: AsyncSession,
    *,
    category: str,
    raw_name: str,
    model: str,
    gateway: ModelGateway | None = None,
) -> str | None:
    """对一个未命中目录的器具输入做"搜索确认"。返回新建的 candidate id；无需落候选则 None。"""
    name = (raw_name or "").strip()
    if not name or category not in EQUIPMENT_CATEGORIES:
        return None
    gw = gateway or model_gateway
    if not gw.enabled:
        return None
    # 已在目录（规范名或别名命中）→ 无需发现。
    if await resolve_equipment(session, category=category, name=name) is not None:
        return None
    if await candidate_repository.has_open(session, category, name):
        return None

    try:
        data = await chat_json(
            gw,
            model=model,
            messages=[
                {"role": "system", "content": _DISCOVER_SYSTEM},
                {"role": "user", "content": f"器具类别：{_CATEGORY_LABEL.get(category, category)}\n用户输入：{name}"},
            ],
            temperature=0,
            max_tokens=400,
            required_keys=["canonical_name"],
            allowed_keys=["is_real_equipment", "canonical_name", "aliases", "confidence"],
        )
    except ModelJSONError as exc:
        logger.warning("equipment discovery JSON invalid for %r: %s", name, exc)
        return None
    except Exception as exc:  # noqa: BLE001 — 发现失败不影响任何主流程
        logger.warning("equipment discovery model call failed for %r: %s", name, exc)
        return None

    if not data.get("is_real_equipment"):
        return None
    confidence = data.get("confidence")
    if isinstance(confidence, (int, float)) and confidence < 0.6:
        return None
    canonical = str(data.get("canonical_name") or "").strip()
    if not canonical:
        return None
    aliases = [a.strip() for a in (data.get("aliases") or []) if isinstance(a, str) and a.strip()]

    # 模型给的规范名其实已在目录（别名命中）→ 把用户写法 + 别名登记到该实体，不另建候选。
    hit = await resolve_equipment(session, category=category, name=canonical)
    if hit is not None:
        await entity_repository.register_aliases(
            session, hit.id, hit.canonical_name, extra=[name, *aliases], source="discovery"
        )
        return None
    if await entity_repository.exists_active(session, category, canonical):
        return None
    if await candidate_repository.has_open(session, category, canonical):
        return None

    candidate = await candidate_repository.create(
        session,
        entity_type=category,
        title=canonical,
        payload={"name": canonical, "aliases": [name, *aliases]},
        source_table="user_equipment_items",
        source_record_id=None,
        source_user_id=None,
        source_input=name,
    )
    return candidate.id


async def run_equipment_discovery(*, items: list[tuple[str, str]], model: str) -> None:
    """后台任务：对一批未命中目录的器具（(category, raw_name)）逐个做发现。独立 session、失败不外抛。"""
    seen: set[tuple[str, str]] = set()
    todo = [(c, n) for c, n in items if (c, n) not in seen and not seen.add((c, n))]
    if not todo:
        return
    sessionmaker = get_sessionmaker()
    try:
        async with sessionmaker() as session:
            for category, raw_name in todo:
                try:
                    await discover_equipment(session, category=category, raw_name=raw_name, model=model)
                except Exception as exc:  # noqa: BLE001 — 单个失败不影响其余
                    logger.warning("discover_equipment(%s, %r) failed: %s", category, raw_name, exc)
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — 后台发现失败绝不影响对话
        logger.warning("equipment discovery batch failed: %s", exc)


__all__ = ["discover_equipment", "run_equipment_discovery"]
