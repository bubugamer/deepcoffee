from __future__ import annotations

from app.schemas.brew import BrewDraft


def build_local_recap(draft: BrewDraft) -> tuple[str, list[str]]:
    bean = draft.bean_name or "这杯咖啡"
    device = f"用 {draft.device}" if draft.device else ""
    ratio = ""
    if draft.dose_g and draft.water_ml:
        ratio_value = draft.water_ml / draft.dose_g
        ratio_text = f"{int(ratio_value)}" if ratio_value.is_integer() else f"{ratio_value:.1f}"
        ratio = f"，粉水比约 1:{ratio_text}"
    temp = f"，水温 {draft.water_temp_c:g}°C" if draft.water_temp_c else ""
    overall_score = draft.evaluation.overall.score if draft.evaluation and draft.evaluation.overall else None
    score_text = f"，总评 {overall_score}/5" if overall_score is not None else ""

    recap = f"已保存 {bean} 的冲煮记录。{device}{ratio}{temp}{score_text}。"

    suggestions: list[str] = []
    if draft.dose_g and draft.water_ml:
        ratio_value = draft.water_ml / draft.dose_g
        if ratio_value < 14:
            suggestions.append("下次可以稍微增加水量，观察甜感和尾段是否更舒展。")
        elif ratio_value > 17:
            suggestions.append("下次可以稍微减少水量，观察风味集中度是否提升。")
        else:
            suggestions.append("粉水比在常见手冲范围内，下一次可以优先微调研磨或水温。")
    if draft.water_temp_c:
        if draft.water_temp_c < 90:
            suggestions.append("水温偏低时容易萃取不足，可以尝试提高 1-2°C。")
        elif draft.water_temp_c > 95:
            suggestions.append("水温偏高时可能带出苦涩，可以尝试降低 1-2°C。")
    if not suggestions:
        suggestions.append("下次补充粉量、水量和水温后，可以得到更具体的复盘建议。")

    return recap, suggestions[:3]
