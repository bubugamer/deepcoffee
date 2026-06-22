"""把自然语言豆子描述解析成豆卡草稿（本地启发式规则版）。

和 input_parser（冲煮）同思路：正则 + 关键词词表抽取结构化字段，不写库。
未来接入模型网关后可升级为模型解析（同样产出 BeanDraft，端点不变）；当前模型调用被
渠道 key / token 卡住，先用本地规则跑通，保证降级可用。

只抽取**可成为公共实体事实**的客观字段（烘焙商、产地、处理法、品种…）；用户主观风味
理念不在这里强行结构化（留给用户在豆卡里补填）。
"""

from __future__ import annotations

import re

from app.schemas.bean import BeanDraft, BeanFlavor, default_flavor

# 处理法词表（含中英与常见别名）。
_PROCESS_PATTERNS: list[tuple[str, str]] = [
    ("双重厌氧", "双重厌氧"),
    ("厌氧日晒", "厌氧日晒"),
    ("厌氧水洗", "厌氧水洗"),
    ("厌氧", "厌氧"),
    ("anaerobic", "厌氧"),
    ("二氧化碳浸渍", "二氧化碳浸渍"),
    ("carbonic", "二氧化碳浸渍"),
    ("cm", "二氧化碳浸渍"),
    ("红蜜", "红蜜处理"),
    ("黄蜜", "黄蜜处理"),
    ("黑蜜", "黑蜜处理"),
    ("白蜜", "白蜜处理"),
    ("蜜处理", "蜜处理"),
    ("honey", "蜜处理"),
    ("水洗", "水洗"),
    ("washed", "水洗"),
    ("日晒", "日晒"),
    ("natural", "日晒"),
    ("湿刨", "湿刨"),
]

# 品种词表。
_VARIETAL_PATTERNS: list[tuple[str, str]] = [
    ("瑰夏", "瑰夏"),
    ("geisha", "瑰夏"),
    ("gesha", "瑰夏"),
    ("帕卡马拉", "帕卡马拉"),
    ("pacamara", "帕卡马拉"),
    ("卡杜艾", "卡杜艾"),
    ("catuai", "卡杜艾"),
    ("卡杜拉", "卡杜拉"),
    ("caturra", "卡杜拉"),
    ("铁皮卡", "铁皮卡"),
    ("typica", "铁皮卡"),
    ("波旁", "波旁"),
    ("bourbon", "波旁"),
    ("sl28", "SL28"),
    ("sl34", "SL34"),
    ("伊卡图", "伊卡图"),
    ("原生种", "原生种"),
    ("heirloom", "原生种"),
]

# 产地（国家 / 知名产区）词表。
_ORIGIN_PATTERNS: list[tuple[str, str]] = [
    ("耶加雪菲", "埃塞俄比亚 耶加雪菲"),
    ("耶加", "埃塞俄比亚 耶加雪菲"),
    ("西达摩", "埃塞俄比亚 西达摩"),
    ("古吉", "埃塞俄比亚 古吉"),
    ("埃塞俄比亚", "埃塞俄比亚"),
    ("埃塞", "埃塞俄比亚"),
    ("ethiopia", "埃塞俄比亚"),
    ("巴拿马", "巴拿马"),
    ("panama", "巴拿马"),
    ("哥伦比亚", "哥伦比亚"),
    ("colombia", "哥伦比亚"),
    ("肯尼亚", "肯尼亚"),
    ("kenya", "肯尼亚"),
    ("危地马拉", "危地马拉"),
    ("guatemala", "危地马拉"),
    ("哥斯达黎加", "哥斯达黎加"),
    ("costa rica", "哥斯达黎加"),
    ("卢旺达", "卢旺达"),
    ("rwanda", "卢旺达"),
    ("玻利维亚", "玻利维亚"),
    ("bolivia", "玻利维亚"),
    ("巴西", "巴西"),
    ("brazil", "巴西"),
    ("云南", "中国 云南"),
    ("yunnan", "中国 云南"),
]

# 常见风味描述词（出现即收进 flavor.notes）。
_FLAVOR_WORDS = [
    "茉莉", "花香", "柑橘", "橘子", "柠檬", "莓果", "草莓", "蓝莓", "树莓", "水蜜桃", "桃",
    "热带水果", "百香果", "芒果", "凤梨", "红茶", "乌龙", "巧克力", "可可", "坚果", "焦糖",
    "蜂蜜", "红酒", "发酵", "葡萄", "杏", "甜瓜", "荔枝", "玫瑰",
]


def _first_match(text: str, patterns: list[tuple[str, str]]) -> str | None:
    lowered = text.lower()
    for needle, canonical in patterns:
        if needle in lowered:
            return canonical
    return None


def _all_matches(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for needle, canonical in patterns:
        if needle in lowered and canonical not in found:
            found.append(canonical)
    return found


def _extract_roaster(text: str) -> str | None:
    # 「X 烘焙」「X 咖啡」「by X」等弱模式；抽不准就留空，交给用户补。
    m = re.search(r"([一-鿿A-Za-z0-9]{2,12})\s*(?:烘焙(?:商|工坊)?|咖啡(?:烘焙)?)", text)
    if m:
        return m.group(1).strip()
    m = re.search(r"\bby\s+([A-Za-z0-9 ]{2,30})", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _extract_flavor_notes(text: str) -> list[str]:
    notes: list[str] = []
    # 显式「风味：A、B、C」段优先。
    m = re.search(r"(?:风味|flavou?r|notes?)[：:，,\s]+([^。\n]{2,60})", text, re.IGNORECASE)
    segment = m.group(1) if m else text
    for word in _FLAVOR_WORDS:
        if word in segment and word not in notes:
            notes.append(word)
    return notes[:6]


def _extract_name(text: str, roaster: str | None, origin: str | None, varietals: list[str]) -> str | None:
    # 取第一行 / 第一个分句作为豆名候选；太长则截断。
    head = re.split(r"[，,。\n]", text.strip(), maxsplit=1)[0].strip()
    if head and 1 < len(head) <= 60:
        return head
    # 退化：用「产地 + 品种」拼一个可读名。
    parts = [p for p in [origin, " ".join(varietals)] if p]
    if parts:
        return " ".join(parts)[:60]
    return head[:60] or None


def build_flavor(notes: list[str]) -> BeanFlavor:
    """风味：有明确写出的关键词就保存标签；无官方维度时不自动生成默认维度。

    本地解析和模型解析（bean_parse_ai）共用，保证两条路径产出的豆卡风味结构一致。
    """
    if not notes:
        return default_flavor()
    return BeanFlavor(notes=notes, source="user", scale_max=5, axes=[])


def assess_bean_draft(draft: BeanDraft) -> tuple[float, list[str], str | None]:
    """按必填字段完整度算 confidence / low_confidence / clarification。模型与本地共用。"""
    important = {
        "name": draft.name,
        "roaster_name": draft.roaster_name,
        "origin_name": draft.origin_name,
        "process_name": draft.process_name,
    }
    low_confidence = [field for field, value in important.items() if not value]
    confidence = round((len(important) - len(low_confidence)) / len(important), 2)
    clarification = None
    if low_confidence:
        clarification = "请补充豆名、烘焙商、产地或处理法中缺失的信息。"
    return confidence, low_confidence, clarification


def parse_bean_input(text: str) -> tuple[BeanDraft, float, list[str], str | None]:
    process = _first_match(text, _PROCESS_PATTERNS)
    varietals = _all_matches(text, _VARIETAL_PATTERNS)
    origin = _first_match(text, _ORIGIN_PATTERNS)
    roaster = _extract_roaster(text)
    notes = _extract_flavor_notes(text)
    name = _extract_name(text, roaster, origin, varietals)

    draft = BeanDraft(
        name=name,
        roaster_name=roaster,
        origin_name=origin,
        process_name=process,
        varietal_names=varietals,
        flavor=build_flavor(notes),
        private_notes=None,
    )
    confidence, low_confidence, clarification = assess_bean_draft(draft)
    return draft, confidence, low_confidence, clarification
