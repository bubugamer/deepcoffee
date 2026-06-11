"""Coffea 建议冲煮参数生成（本地启发式版）。

按豆子的处理法 / 品种给一组合理的手冲起手参数。产出一个完整 BrewDraft，落为
`ai_suggestion` 冲煮记录（系统归属、用户不可见），豆子用 recommended_record_id 指向它。

未来接入模型网关（new-api）后可换成模型生成（同样产出 BrewDraft，端点不变）；当前模型
调用被渠道 key / token 卡住，先用本地规则保证降级可用。
"""

from __future__ import annotations

from app.schemas.bean import Bean
from app.schemas.brew import BrewDraft
from app.services.brew_validation import complete_brew_parameters

# 处理法 → (水温℃, 粉水比, 备注)。日晒/厌氧偏低温拉甜感、避免发酵感过冲；水洗偏高温拉明亮度。
_PROCESS_PROFILE: dict[str, tuple[float, float, str]] = {
    "水洗": (92.0, 15.0, "水洗豆偏高温拉明亮酸质与干净度"),
    "日晒": (90.0, 16.0, "日晒豆偏低温、略大粉水比，突出甜感、收敛发酵感"),
    "蜜处理": (91.0, 15.5, "蜜处理介于水洗与日晒之间，中温中比例"),
    "红蜜处理": (91.0, 15.5, "蜜处理介于水洗与日晒之间，中温中比例"),
    "黄蜜处理": (91.0, 15.5, "蜜处理介于水洗与日晒之间，中温中比例"),
    "黑蜜处理": (90.5, 15.5, "黑蜜糖分高，略降温避免甜腻发苦"),
    "厌氧": (89.0, 16.0, "厌氧发酵风味强，低温小流速收敛发酵感"),
    "厌氧日晒": (89.0, 16.0, "厌氧发酵风味强，低温小流速收敛发酵感"),
    "二氧化碳浸渍": (89.0, 16.0, "CM 发酵风味强，低温收敛"),
}

_DEFAULT_PROFILE = (92.0, 16.0, "通用手冲起手参数，先跑一杯再按口味微调")


def generate_recommended_params(bean: Bean) -> tuple[BrewDraft, str]:
    """返回 (建议参数草稿, Coffea 备注)。草稿已补全粉/水/比三项。"""
    process = bean.process or ""
    temp, ratio_value, note = _DEFAULT_PROFILE
    for key, profile in _PROCESS_PROFILE.items():
        if key in process:
            temp, ratio_value, note = profile
            break

    # 瑰夏等高香气品种：略降温、略大比例，避免过萃压抑花香。
    varietal_text = " ".join(bean.varietal)
    if "瑰夏" in varietal_text:
        temp -= 1.0
        ratio_value = max(ratio_value, 16.0)
        note += "；瑰夏高香气，降温并放大粉水比保留花香"

    dose_g = 15.0
    draft = BrewDraft(
        bean_name=bean.name,
        origin=bean.origin,
        roaster=bean.roaster,
        process=bean.process,
        varietal=varietal_text or None,
        device="V60",
        grinder="通用磨（中度研磨）",
        grind_setting="中度",
        dose_g=dose_g,
        water_temp_c=temp,
        ratio=f"1:{ratio_value:g}",
        brew_time_seconds=150,
        notes=f"Coffea 建议参数：{note}",
    )
    draft = complete_brew_parameters(draft)
    return draft, note


recommend_service_note = "local-heuristic"
