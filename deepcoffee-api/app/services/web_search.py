"""Brave Search 客户端（web_verify §9 的「检索」阶段）。

只负责把用户问题送进 Brave Search、整理成结构化来源摘要交给上层综合。
无 key / 网络错 / 非 200 / 无结果一律返回空列表（不抛），让 web_verify 优雅降级回知识库。
复用项目已有的 httpx，不引新依赖。
"""

from __future__ import annotations

import logging
import re
from datetime import date

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_TAG_RE = re.compile(r"<[^>]+>")  # Brave 的 description 会带 <strong> 高亮标签，喂模型前去掉
_PUNCT_RE = re.compile(r"[？?。，,、！!：:；;…\s]+")  # 提炼检索 query 时去标点/空白

# 检索 query 去口语化：用户原话常含「帮我核实一下 / 网上 / 怎么说」等口语，会稀释检索。
# 去掉这些噪声词，让 Brave 聚焦到产品/实体本身（口碑/评价由模型从检索结果里综合）。
_QUERY_NOISE = (
    "帮我核实一下", "帮我核实", "帮我查一下", "帮我查查", "帮我查", "帮我看一下", "帮我看看", "帮我看",
    "我想知道", "我想了解", "想问一下", "想问问", "请问",
    "网络上", "网上说", "网上", "有人说", "大家说", "听说",
    "口碑如何", "口碑怎么样", "评价如何", "评价怎么样", "怎么说", "怎么样", "如何",
    "的最新", "最新", "和口碑", "口碑", "的评价", "评价", "的评论", "评论",
)


class WebSource(BaseModel):
    """一条检索来源（标题 / 链接 / 摘要 / 发布时间 / 访问时间）。"""

    title: str
    url: str
    snippet: str = ""
    published: str | None = None  # 来源发布时间（Brave page_age/age），可能为空
    accessed: str  # 访问日期 YYYY-MM-DD（来源没给发布时间时用来标注时效）


def _clean(text: str | None) -> str:
    return _TAG_RE.sub("", str(text or "")).strip()


def build_search_query(message: str) -> str:
    """从用户消息提炼检索 query：去口语噪声词与标点，聚焦实体本身。

    清洗后过短（可能把实体也误删了）时退回原文去标点版，避免搜了个空。
    """
    raw = message or ""
    q = raw
    for w in _QUERY_NOISE:
        q = q.replace(w, " ")
    q = _PUNCT_RE.sub(" ", q).strip()
    if len(q) < 2:
        q = _PUNCT_RE.sub(" ", raw).strip()
    return q


async def search(query: str, *, api_key: str | None, count: int = 5) -> list[WebSource]:
    """检索并返回结构化来源；无 key / 空查询 / 出错 / 无结果 → []（让上层降级）。"""
    if not api_key or not query.strip():
        return []
    today = date.today().isoformat()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                BRAVE_SEARCH_URL,
                params={"q": query.strip(), "count": max(1, min(count, 20))},
                headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            )
        if resp.status_code != 200:
            logger.warning("brave search non-200 (%s): %s", resp.status_code, resp.text[:200])
            return []
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — 检索失败即降级，绝不打断对话
        logger.warning("brave search failed: %s", exc)
        return []

    results = ((data.get("web") or {}).get("results")) or []
    sources: list[WebSource] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        title = item.get("title")
        if not url or not title:
            continue
        sources.append(
            WebSource(
                title=_clean(title),
                url=str(url),
                snippet=_clean(item.get("description")),
                published=(item.get("page_age") or item.get("age") or None),
                accessed=today,
            )
        )
    return sources
