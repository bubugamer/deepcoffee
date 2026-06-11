from __future__ import annotations

import re

from app.core.errors import AppError
from app.schemas.brew import BrewDraft


def parse_ratio_value(ratio: str | None = None, ratio_value: float | None = None) -> float | None:
    if ratio_value is not None:
        return float(ratio_value)
    if ratio is None:
        return None

    text = ratio.strip().lower().replace("：", ":").replace(" ", "")
    if not text:
        return None

    numeric = re.fullmatch(r"(\d+(?:\.\d+)?)", text)
    if numeric:
        return float(numeric.group(1))

    one_to_n = re.fullmatch(r"1[:/](\d+(?:\.\d+)?)", text)
    if one_to_n:
        return float(one_to_n.group(1))

    amount_pair = re.fullmatch(r"(\d+(?:\.\d+)?)[：:/](\d+(?:\.\d+)?)", text)
    if amount_pair:
        dose = float(amount_pair.group(1))
        water = float(amount_pair.group(2))
        if dose > 0:
            return water / dose

    raise AppError(
        422,
        "invalid_brew_ratio",
        "粉水比格式不正确。请使用 1:15、1:15.5 或 15 这样的格式。",
        details={"field": "draft.ratio"},
    )


def format_ratio(ratio_value: float | None) -> str | None:
    if ratio_value is None:
        return None
    ratio_value = float(ratio_value)
    if ratio_value.is_integer():
        return f"1:{int(ratio_value)}"
    return f"1:{ratio_value:.2f}".rstrip("0").rstrip(".")


def _rounded(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def complete_brew_parameters(draft: BrewDraft) -> BrewDraft:
    ratio_value = parse_ratio_value(draft.ratio, draft.ratio_value)
    dose_g = draft.dose_g
    water_ml = draft.water_ml

    provided_count = sum(value is not None for value in (dose_g, water_ml, ratio_value))
    if provided_count < 2:
        raise AppError(
            422,
            "brew_ratio_fields_incomplete",
            "粉量、水量、粉水比需要至少提供其中两项，后端会自动换算第三项。",
            details={"fields": ["draft.dose_g", "draft.water_ml", "draft.ratio"]},
        )

    if ratio_value is None and dose_g is not None and water_ml is not None:
        ratio_value = water_ml / dose_g
    elif water_ml is None and dose_g is not None and ratio_value is not None:
        water_ml = dose_g * ratio_value
    elif dose_g is None and water_ml is not None and ratio_value is not None:
        dose_g = water_ml / ratio_value

    return draft.model_copy(
        update={
            "dose_g": _rounded(dose_g),
            "water_ml": _rounded(water_ml),
            "ratio_value": _rounded(ratio_value),
            "ratio": format_ratio(ratio_value),
        }
    )


def validate_confirm_draft(draft: BrewDraft) -> BrewDraft:
    draft = complete_brew_parameters(draft)
    missing: list[dict[str, str]] = []

    required_strings = {
        "draft.bean_name": draft.bean_name,
        "draft.device": draft.device,
        "draft.grinder": draft.grinder,
        "draft.grind_setting": draft.grind_setting,
    }
    for field, value in required_strings.items():
        if value is None or not value.strip():
            missing.append({"field": field, "reason": "必填"})

    required_values = {
        "draft.dose_g": draft.dose_g,
        "draft.water_ml": draft.water_ml,
        "draft.ratio_value": draft.ratio_value,
        "draft.water_temp_c": draft.water_temp_c,
        "draft.brew_time_seconds": draft.brew_time_seconds,
    }
    for field, value in required_values.items():
        if value is None:
            missing.append({"field": field, "reason": "必填或需可换算"})

    if missing:
        raise AppError(
            422,
            "brew_confirm_missing_required_fields",
            "确认保存冲煮记录前，请补齐豆名、器具、粉水参数、水温、磨豆机、研磨刻度和总冲煮时间。",
            details={"missing": missing},
        )

    return draft
