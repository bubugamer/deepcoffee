"""常见磨豆机刻度参考表（bean_recommend_params 提示词注入用）。

收录约 15 款常见磨豆机的刻度单位、手冲常用范围与中度参考值，按用户器具资料里的
磨豆机名称做别名匹配，命中的条目格式化注入 BEAN_RECOMMEND_USER_TEMPLATE 的
{grinder_reference} 段，让模型给出具体刻度区间而不是只会「中度偏粗」。

所有数值都是「起手参考区间」而非精确值——同型号不同批次/磨损度也有差异，提示词
侧已要求模型注明仅供起手参考。

数据同步约定：本表与知识库文章 knowledge/equipment/grinders/磨豆机刻度对照表.md
是同一份数据的两个形态（代码喂提示词 / 文档给人读），修改任一侧请同步另一侧。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class GrinderScale:
    canonical_name: str
    aliases: tuple[str, ...]
    scale_unit: str  # 格 / 圈 / 档
    pour_over_range: str  # 手冲常用范围
    medium_ref: str  # 中度参考（可直接作为 grind_setting 文案）
    note: str


GRINDER_SCALES: tuple[GrinderScale, ...] = (
    GrinderScale(
        canonical_name="Comandante C40",
        aliases=("comandante c40", "comandante", "c40"),
        scale_unit="格",
        pour_over_range="18–28 格",
        medium_ref="22–26 格（中度）",
        note="逆时针放粗；浅烘可向 26–28 格放粗，深烘可收到 18–22 格。",
    ),
    GrinderScale(
        canonical_name="MAVO 幻刺 Pro",
        aliases=("mavo 幻刺 pro", "mavo幻刺pro", "mavo 幻刺", "幻刺 pro", "幻刺pro", "幻刺", "mavo"),
        scale_unit="数字刻度（外调旋钮）",
        pour_over_range="约 7–12",
        medium_ref="约 9–11（中度）",
        note="外调 120 格/圈、每格 0.0167mm；数字越大越粗、可到负数（负数最细），重量归零。意式约 2–4，杯测约 6.3。与 C40 换算：C40≈17 格对应幻刺 6.3，C40 每粗 1 格≈幻刺 +0.5（C40 19–25 格区间最接近）。数值多为用户实测/换算，较粗略。",
    ),
    GrinderScale(
        canonical_name="1zpresso ZP6（含 ZP6S 特调版）",
        aliases=("zp6s", "zp6 特调", "zp6特调", "zp6"),
        scale_unit="圈",
        pour_over_range="4.0–6.0 圈",
        medium_ref="4.5–5.5 圈（中度偏粗）",
        note="高分离度刀盘，偏淡偏空时调细 0.2–0.3 圈；浅烘花果豆常用 4.5–5.0 圈。",
    ),
    GrinderScale(
        canonical_name="1zpresso JX",
        aliases=("jx-pro", "jxpro", "jx pro", "jx"),
        scale_unit="圈",
        pour_over_range="2.5–3.5 圈（JX-Pro 约 3.0–4.5 圈）",
        medium_ref="3.0 圈上下（中度）",
        note="外调式；JX-Pro 每圈 40 格更细分，调整以 0.5 圈/2–4 格为步进。",
    ),
    GrinderScale(
        canonical_name="1zpresso J-Max",
        aliases=("j-max", "jmax", "j max"),
        scale_unit="圈",
        pour_over_range="4.0–6.0 圈",
        medium_ref="4.5–5.5 圈（中度）",
        note="每格约 8.8µm、细分极多；微调建议一次 3–5 格。",
    ),
    GrinderScale(
        canonical_name="1zpresso K-Plus / K-Max",
        aliases=("k-plus", "kplus", "k plus", "k-max", "kmax", "k max"),
        scale_unit="格（外圈数字）",
        pour_over_range="外圈 7–10",
        medium_ref="外圈 8–9（中度）",
        note="K 系列每格约 22µm；意式区间在外圈 2–4，手冲不要低于 6。",
    ),
    GrinderScale(
        canonical_name="1zpresso Q2",
        aliases=("q2",),
        scale_unit="格",
        pour_over_range="18–26 格",
        medium_ref="20–24 格（中度）",
        note="内调式，归零后顺时针数格；便携定位，细分较少，一次调 1–2 格。",
    ),
    GrinderScale(
        canonical_name="泰摩 C2 / C3",
        aliases=("泰摩 c2", "泰摩c2", "泰摩 c3", "泰摩c3", "timemore c2", "timemore c3", "c3", "c2"),
        scale_unit="格",
        pour_over_range="16–24 格",
        medium_ref="18–22 格（中度）",
        note="归零后逆时针数格；偏酸偏淡调细 1–2 格，偏苦偏涩放粗 1–2 格。",
    ),
    GrinderScale(
        canonical_name="泰摩 栗子X",
        aliases=("栗子x", "栗子 x", "chestnut x"),
        scale_unit="档（外调旋钮）",
        pour_over_range="6–9 档",
        medium_ref="7–8 档（中度）",
        note="外调带数字窗；浅烘可在 6–7 档，深烘 8–9 档。",
    ),
    GrinderScale(
        canonical_name="Kingrinder K4 / K6",
        aliases=("kingrinder k4", "kingrinder k6", "kingrinder", "k6", "k4"),
        scale_unit="格",
        pour_over_range="60–90 格",
        medium_ref="70–80 格（中度）",
        note="外调式、每格约 16µm；意式约 20–40 格，手冲建议不低于 50 格。",
    ),
    GrinderScale(
        canonical_name="Mahlkönig EK43",
        aliases=("ek43s", "ek43", "ek 43"),
        scale_unit="档（刻度盘）",
        pour_over_range="7–9.5 档",
        medium_ref="8–9 档（中度）",
        note="刀盘校准差异大，同档位不同机器可差 0.5–1 档；以杯感微调为准。",
    ),
    GrinderScale(
        canonical_name="Fellow Ode Gen 2",
        aliases=("ode gen2", "ode gen 2", "fellow ode", "ode"),
        scale_unit="档（1–11，每档 2 小步）",
        pour_over_range="4–7 档",
        medium_ref="5–6 档（中度）",
        note="专为手冲/滤泡设计，不适合意式；浅烘可收到 4–5 档。",
    ),
    GrinderScale(
        canonical_name="Baratza Encore",
        aliases=("baratza encore", "encore"),
        scale_unit="档（0–40）",
        pour_over_range="13–20 档",
        medium_ref="15–18 档（中度）",
        note="入门电磨细粉偏多；偏涩时放粗 2 档并适当降水温。",
    ),
    GrinderScale(
        canonical_name="小飞马 / 小飞鹰",
        aliases=("小飞马", "小飞鹰", "飞马 600n", "飞马600n"),
        scale_unit="档（刻度盘 1–10）",
        pour_over_range="3.5–5 档",
        medium_ref="4 档上下（中度）",
        note="鬼齿/平刀家用电磨，细粉较多；手冲常用 3.5–4.5 档，配合筛粉更干净。",
    ),
)

NO_REFERENCE_TEXT = "（无内置刻度资料）"

def _norm(value: str) -> str:
    return "".join((value or "").lower().split()).replace("-", "").replace("_", "")


# 别名长的优先匹配，避免「zp6」抢先命中「zp6s」、「k4」抢先命中「ek43」。
_ALIAS_INDEX: list[tuple[str, GrinderScale]] = sorted(
    ((_norm(alias), scale) for scale in GRINDER_SCALES for alias in scale.aliases),
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def lookup_grinder_scale(name: str | None) -> GrinderScale | None:
    """按别名做小写化、去空格/连字符后的包含匹配；未知型号返回 None。"""
    text = _norm(name or "")
    if not text:
        return None
    for alias, scale in _ALIAS_INDEX:
        if alias in text:
            return scale
    return None


def format_grinder_reference(names: Iterable[str | None]) -> str:
    """对一组磨豆机名做 lookup，命中条目格式化为提示词参考段；全部未命中返回占位文案。"""
    seen: set[str] = set()
    lines: list[str] = []
    for name in names:
        scale = lookup_grinder_scale(name)
        if scale is None or scale.canonical_name in seen:
            continue
        seen.add(scale.canonical_name)
        lines.append(
            f"- {scale.canonical_name}（刻度单位：{scale.scale_unit}）："
            f"手冲常用 {scale.pour_over_range}；中度参考 {scale.medium_ref}。{scale.note}"
        )
    return "\n".join(lines) if lines else NO_REFERENCE_TEXT
