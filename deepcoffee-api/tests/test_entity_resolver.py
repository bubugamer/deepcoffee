from __future__ import annotations

import asyncio
from types import SimpleNamespace

import app.services.coffea_executor as ce
from app.schemas.coffea import ActionResult
from app.services.entity_resolver import resolve_user_bean

_BEANS = [
    {"bean_id": "b1", "name": "圣洁庄园 苏丹汝魅 厌氧日晒 家族典藏系列"},
    {"bean_id": "b2", "name": "瑰夏村 1931"},
]


def test_resolve_user_bean_prefix_unique_match() -> None:
    # 解析名是豆卡全名的前缀 → 唯一命中
    assert resolve_user_bean("圣洁庄园 苏丹汝魅 厌氧日晒", beans=_BEANS)["bean_id"] == "b1"


def test_resolve_user_bean_substring_match() -> None:
    assert resolve_user_bean("苏丹汝魅", beans=_BEANS)["bean_id"] == "b1"


def test_resolve_user_bean_active_bean_priority() -> None:
    # 空解析名 + 活跃豆 → 用活跃豆
    assert resolve_user_bean("", beans=_BEANS, active_bean=_BEANS[0])["bean_id"] == "b1"


def test_resolve_user_bean_unrelated_returns_none() -> None:
    assert resolve_user_bean("耶加雪菲 沃卡", beans=_BEANS) is None


def test_resolve_user_bean_ambiguous_returns_none() -> None:
    beans = [
        {"bean_id": "x1", "name": "瑰夏 红标"},
        {"bean_id": "x2", "name": "瑰夏 蓝标"},
    ]
    # "瑰夏" 同时是两支的子串 → 多义不认
    assert resolve_user_bean("瑰夏", beans=beans) is None


def _fake_equipment_resolver(mapping):
    async def _resolve(session, *, category, name):
        canonical = mapping.get((category, name))
        return SimpleNamespace(canonical_name=canonical) if canonical else None
    return _resolve


def test_resolve_brew_draft_rewrites_to_canonical_and_links_bean(monkeypatch) -> None:
    monkeypatch.setattr(ce, "resolve_equipment", _fake_equipment_resolver({
        ("brewer", "V60"): "Hario V60",
        ("grinder", "1Zpresso ZP6 Special"): "1Zpresso ZP6S",
        ("filter_media", "纸滤"): "纸滤",
        ("water", "农夫山泉"): "农夫山泉",
    }))
    draft = {
        "bean_name": "圣洁庄园 苏丹汝魅 厌氧日晒", "brew_method": "滤杯冲煮", "device": "V60",
        "grinder": "1Zpresso ZP6 Special", "grind_setting": "4.2",
        "filter_media": "纸滤", "water": "农夫山泉",
        "dose_g": 15.0, "water_ml": 240.0, "water_temp_c": 92.0,
    }
    summary = ce._brew_summary(ce.BrewDraft.model_validate(draft))
    r = ActionResult(
        type="brew_record_parse", status="done",
        output={"draft": dict(draft), "missing_fields": ["brew_time_seconds"]},
        message=f"我从你的描述里解析出：{summary}。还缺冲煮时间，确认后保存。",
    )
    unmatched = asyncio.run(ce.resolve_brew_draft_entities(None, [r], beans=_BEANS, active_bean=None))

    d = r.output["draft"]
    assert d["device"] == "Hario V60"
    assert d["grinder"] == "1Zpresso ZP6S"
    assert d["bean_name"] == "圣洁庄园 苏丹汝魅 厌氧日晒 家族典藏系列"
    assert r.output["resolved_bean_id"] == "b1"
    assert "Hario V60" in r.message and "1Zpresso ZP6S" in r.message
    assert unmatched == []  # 全部命中目录,无需后台发现


def test_resolve_brew_draft_reports_unmatched_equipment(monkeypatch) -> None:
    # 目录里没有这台磨 → 不改写,并作为"未命中"返回（供后台搜索确认）。
    monkeypatch.setattr(ce, "resolve_equipment", _fake_equipment_resolver({
        ("brewer", "V60"): "Hario V60",
    }))
    draft = {"bean_name": "某豆", "device": "V60", "grinder": "野鸡牌手摇磨 X1",
             "dose_g": 15.0, "water_ml": 240.0, "water_temp_c": 92.0}
    r = ActionResult(type="brew_record_parse", status="done",
                     output={"draft": dict(draft), "missing_fields": []}, message="x")
    unmatched = asyncio.run(ce.resolve_brew_draft_entities(None, [r], beans=[], active_bean=None))
    assert r.output["draft"]["device"] == "Hario V60"
    assert r.output["draft"]["grinder"] == "野鸡牌手摇磨 X1"  # 未命中,保持原值
    assert ("grinder", "野鸡牌手摇磨 X1") in unmatched
