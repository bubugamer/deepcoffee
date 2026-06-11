"""对话豆卡识图 → 豆卡草稿的转换与识别度评估。

vision 的 image_understanding 输出（bean_fields 等原始 JSON）不直接给用户看；这里把它
转成 BeanDraft + 综合识别度 + 一句人话摘要，供 coffea 链路决定「自动录入」还是「草稿确认」。
"""

from __future__ import annotations

from typing import Any

from app.schemas.bean import BeanDraft, BeanFlavor
from app.services.bean_parser import assess_bean_draft

# bean_fields 与 BeanDraft 同名直传的字段。
_DIRECT_FIELDS = (
    "name",
    "roaster_name",
    "roaster_product_name",
    "coffee_source_name",
    "green_bean_merchant_name",
    "green_bean_product_name",
    "origin_name",
    "process_name",
)
# 没有独立落点的附加信息，并入 private_notes 保留下来。
_NOTE_FIELDS = (("roast_date", "烘焙日期"), ("harvest_date", "采收期"), ("altitude", "海拔"), ("official_recipe", "官方建议"))


def _clean(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def draft_from_bean_fields(data: dict[str, Any]) -> BeanDraft:
    fields = data.get("bean_fields")
    if not isinstance(fields, dict):
        fields = {}
    kwargs: dict[str, Any] = {key: _clean(fields.get(key)) for key in _DIRECT_FIELDS}
    varietals = fields.get("varietal_names")
    kwargs["varietal_names"] = [v.strip() for v in varietals if isinstance(v, str) and v.strip()] if isinstance(varietals, list) else []
    notes = fields.get("flavor_notes")
    flavor_notes = [n.strip() for n in notes if isinstance(n, str) and n.strip()] if isinstance(notes, list) else []
    if flavor_notes:
        kwargs["flavor"] = BeanFlavor(notes=flavor_notes, source="roaster")
    extra_lines = [f"{label}：{_clean(fields.get(key))}" for key, label in _NOTE_FIELDS if _clean(fields.get(key))]
    if extra_lines:
        kwargs["private_notes"] = "\n".join(extra_lines)
    return BeanDraft(**kwargs)


def effective_confidence(data: dict[str, Any], draft: BeanDraft) -> float:
    """vision 自报 confidence 与字段完整度评估取 min，防止模型自报过高。"""
    assessed, _, _ = assess_bean_draft(draft)
    reported = data.get("confidence")
    if isinstance(reported, (int, float)) and 0 <= reported <= 1:
        return round(min(float(reported), assessed), 2)
    return assessed


def summarize_draft(draft: BeanDraft) -> str:
    """只列识别到的字段的一句人话摘要。"""
    parts: list[str] = []
    if draft.name:
        parts.append(draft.name)
    if draft.roaster_name:
        parts.append(f"烘焙商 {draft.roaster_name}")
    if draft.origin_name:
        parts.append(f"产地 {draft.origin_name}")
    if draft.process_name:
        parts.append(f"处理法 {draft.process_name}")
    if draft.varietal_names:
        parts.append(f"品种 {'、'.join(draft.varietal_names)}")
    if draft.flavor and draft.flavor.notes:
        parts.append(f"风味 {'、'.join(draft.flavor.notes[:4])}")
    return " · ".join(parts) if parts else "（没有识别出可用的豆卡信息）"


def ocr_raw_input(data: dict[str, Any]) -> str | None:
    """OCR 原文拼接，作为建档 raw_input 留痕。"""
    ocr = data.get("ocr_text")
    if isinstance(ocr, list):
        lines = [line.strip() for line in ocr if isinstance(line, str) and line.strip()]
        if lines:
            return "\n".join(lines)[:4000]
    return None
