"""磨豆机刻度参考表：别名匹配与提示词参考段格式化。"""

from __future__ import annotations

from app.services.grinder_scales import (
    NO_REFERENCE_TEXT,
    format_grinder_reference,
    lookup_grinder_scale,
)


def test_lookup_exact_and_case_insensitive() -> None:
    assert lookup_grinder_scale("C40").canonical_name == "Comandante C40"
    assert lookup_grinder_scale("comandante c40").canonical_name == "Comandante C40"


def test_lookup_contains_match_with_noise() -> None:
    # 用户存的 grinder 常是组合文本：品牌 + 型号 + 后缀。
    scale = lookup_grinder_scale("1zpresso ZP6S 特调版")
    assert scale is not None
    assert "ZP6" in scale.canonical_name


def test_lookup_zp6_vs_zp6s_share_entry() -> None:
    assert lookup_grinder_scale("zp6").canonical_name == lookup_grinder_scale("ZP6S").canonical_name


def test_lookup_longest_alias_wins() -> None:
    # 「k4」不能抢先命中「ek43」；「jx」不能抢先命中「jx-pro」。
    assert lookup_grinder_scale("EK43").canonical_name == "Mahlkönig EK43"
    assert lookup_grinder_scale("Kingrinder K4").canonical_name == "Kingrinder K4 / K6"
    assert lookup_grinder_scale("JX-Pro").canonical_name == "1zpresso JX"


def test_lookup_spaces_and_hyphens_normalized() -> None:
    assert lookup_grinder_scale(" j - max ").canonical_name == "1zpresso J-Max"
    assert lookup_grinder_scale("泰摩 C2").canonical_name == "泰摩 C2 / C3"


def test_lookup_unknown_returns_none() -> None:
    assert lookup_grinder_scale("无名小磨") is None
    assert lookup_grinder_scale("") is None
    assert lookup_grinder_scale(None) is None


def test_format_reference_hits_and_dedup() -> None:
    text = format_grinder_reference(["C40", "comandante", "ZP6S", None])
    assert text.count("Comandante C40") == 1  # 同一型号去重
    assert "4.5–5.5 圈（中度偏粗）" in text


def test_format_reference_no_hits() -> None:
    assert format_grinder_reference(["无名小磨", None, ""]) == NO_REFERENCE_TEXT
