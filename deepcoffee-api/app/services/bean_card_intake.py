"""对话豆卡识图 → 豆卡草稿的转换与识别度评估。

vision 的 image_understanding 输出（bean_fields 等原始 JSON）不直接给用户看；这里把它
转成 BeanDraft + 综合识别度 + 一句人话摘要，供 coffea 链路决定「自动录入」还是「草稿确认」。
"""

from __future__ import annotations

from typing import Any

from app.schemas.bean import BeanComponent, BeanDraft, BeanFlavor, FlavorAxis
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
    "altitude_text",
    "harvest_date_text",
    "roast_date_text",
    "net_weight_text",
)
# 没有独立落点的附加信息，并入 private_notes 保留下来。
_ALIASES = {
    "altitude_text": ("altitude",),
    "harvest_date_text": ("harvest_date",),
    "roast_date_text": ("roast_date",),
    "net_weight_text": ("net_weight", "weight"),
}
_NOTE_FIELDS = (("official_recipe", "官方建议"),)


def _clean(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _field(fields: dict[str, Any], key: str) -> str | None:
    direct = _clean(fields.get(key))
    if direct:
        return direct
    for alias in _ALIASES.get(key, ()):
        value = _clean(fields.get(alias))
        if value:
            return value
    return None


def _str_list(value: Any) -> list[str]:
    return [v.strip() for v in value if isinstance(v, str) and v.strip()] if isinstance(value, list) else []


def _flavor_axes(value: Any) -> list[FlavorAxis]:
    if not isinstance(value, list):
        return []
    axes: list[FlavorAxis] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label = _clean(item.get("label"))
        if not label:
            continue
        raw = item.get("value")
        axes.append(FlavorAxis(label=label, value=float(raw) if isinstance(raw, (int, float)) else None))
    return axes


def _components(value: Any) -> list[BeanComponent]:
    if not isinstance(value, list):
        return []
    out: list[BeanComponent] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        out.append(
            BeanComponent(
                origin_name=_clean(item.get("origin_name")),
                coffee_source_name=_clean(item.get("coffee_source_name")),
                process_name=_clean(item.get("process_name")),
                varietal_names=_str_list(item.get("varietal_names")),
                altitude_text=_clean(item.get("altitude_text")) or _clean(item.get("altitude")),
                share_text=_clean(item.get("share_text")) or _clean(item.get("share")),
                notes=_clean(item.get("notes")),
            )
        )
    return out


def draft_from_bean_fields(data: dict[str, Any]) -> BeanDraft:
    fields = data.get("bean_fields")
    if not isinstance(fields, dict):
        fields = {}
    kwargs: dict[str, Any] = {key: _field(fields, key) for key in _DIRECT_FIELDS}
    kwargs["varietal_names"] = _str_list(fields.get("varietal_names"))
    kwargs["bean_components"] = _components(fields.get("bean_components"))
    flavor_notes = _str_list(fields.get("flavor_notes"))
    axes = _flavor_axes(fields.get("flavor_axes"))
    if flavor_notes or axes:
        kwargs["flavor"] = BeanFlavor(notes=flavor_notes, source="roaster", axes=axes)
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
    if draft.altitude_text:
        parts.append(f"海拔 {draft.altitude_text}")
    if draft.bean_components:
        parts.append(f"豆源 {len(draft.bean_components)} 组")
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
