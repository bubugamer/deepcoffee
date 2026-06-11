from __future__ import annotations

import re

from app.schemas.brew import BrewDraft


def _number_before(text: str, suffixes: tuple[str, ...]) -> float | None:
    suffix_pattern = "|".join(re.escape(suffix) for suffix in suffixes)
    match = re.search(rf"(\d+(?:\.\d+)?)\s*(?:{suffix_pattern})", text, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1))


def _brew_time_seconds(text: str) -> int | None:
    minute_second = re.search(r"(\d+)\s*[:：]\s*(\d{1,2})", text)
    if minute_second:
        return int(minute_second.group(1)) * 60 + int(minute_second.group(2))

    zh_time = re.search(r"(\d+)\s*分(?:钟)?\s*(\d+)?\s*秒?", text)
    if zh_time:
        seconds = int(zh_time.group(1)) * 60
        if zh_time.group(2):
            seconds += int(zh_time.group(2))
        return seconds

    seconds_only = re.search(r"(\d+)\s*秒", text)
    if seconds_only:
        return int(seconds_only.group(1))
    return None


def parse_brew_input(text: str) -> tuple[BrewDraft, float, list[str], str | None]:
    lowered = text.lower()
    device = None
    for candidate in ("v60", "aeropress", "origami", "kalita", "chemex", "espresso"):
        if candidate in lowered:
            device = candidate.upper() if candidate == "v60" else candidate.title()
            break

    grinder = None
    grinder_match = re.search(r"(comandante\s*c40|c40|ek43|k-ultra|zp6|timemore|泰摩|司令官)", text, re.IGNORECASE)
    if grinder_match:
        grinder = grinder_match.group(0).strip(" ，,。")

    grind_setting = None
    grind_match = re.search(r"(?:#|刻度\s*)(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if grind_match:
        grind_setting = f"#{grind_match.group(1)}"

    dose_g = _number_before(text, ("g", "克"))
    water_ml = _number_before(text, ("ml", "毫升"))
    temp_c = _number_before(text, ("°c", "℃", "度"))
    brew_time_seconds = _brew_time_seconds(text)

    bean_name = None
    bean_match = re.search(r"冲(?:了|的)?(.+?)(?:，|,|\s+\d+\s*(?:g|克)|$)", text)
    if bean_match:
        bean_name = bean_match.group(1).strip(" 的了，,。")

    draft = BrewDraft(
        bean_name=bean_name,
        device=device,
        grinder=grinder,
        grind_setting=grind_setting,
        dose_g=dose_g,
        water_ml=water_ml,
        water_temp_c=temp_c,
        brew_time_seconds=brew_time_seconds,
        notes=text,
    )

    confidence, low_confidence, clarification = assess_brew_draft(draft)
    return draft, confidence, low_confidence, clarification


def assess_brew_draft(draft: BrewDraft) -> tuple[float, list[str], str | None]:
    """按关键字段完整度算 confidence / low_confidence / clarification。模型与本地共用。"""
    important_fields = {
        "bean_name": draft.bean_name,
        "device": draft.device,
        "dose_g": draft.dose_g,
        "water_ml": draft.water_ml,
        "water_temp_c": draft.water_temp_c,
        "grinder": draft.grinder,
        "grind_setting": draft.grind_setting,
        "brew_time_seconds": draft.brew_time_seconds,
    }
    low_confidence = [field for field, value in important_fields.items() if value is None]
    confidence = round((len(important_fields) - len(low_confidence)) / len(important_fields), 2)
    clarification = None
    if low_confidence:
        clarification = "请补充豆子、器具、粉量、水量或水温中缺失的信息。"
    return confidence, low_confidence, clarification
