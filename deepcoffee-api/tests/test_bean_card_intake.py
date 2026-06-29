from __future__ import annotations

from app.services.bean_card_intake import (
    draft_from_bean_fields,
    effective_confidence,
    ocr_raw_input,
    summarize_draft,
)


def _data(**bean_fields):
    return {"image_type": "bean_card", "bean_fields": bean_fields}


def test_draft_maps_direct_fields_and_flavor_notes() -> None:
    draft = draft_from_bean_fields(
        _data(
            name=" 千峰庄园 帕卡马拉 ",
            roaster_name="Coffeebuff",
            origin_name="巴拿马",
            process_name="CM 日晒",
            varietal_names=["帕卡马拉", " ", 42],
            flavor_notes=["草莓", "奶油"],
            roast_date="2026-05-20",
            altitude="1800m",
            net_weight="100g",
            bean_components=[
                {
                    "origin_name": "巴拿马",
                    "coffee_source_name": "千峰庄园",
                    "process_name": "水洗",
                    "varietal_names": ["瑰夏"],
                    "altitude": "1800m",
                }
            ],
        )
    )
    assert draft.name == "千峰庄园 帕卡马拉"
    assert draft.roaster_name == "Coffeebuff"
    assert draft.flavor is not None and draft.flavor.notes == ["草莓", "奶油"]
    assert draft.flavor.source == "roaster"
    assert draft.roast_date_text == "2026-05-20"
    assert draft.net_weight_text == "100g"
    assert len(draft.bean_components) == 1
    assert draft.bean_components[0].coffee_source_name == "千峰庄园"
    assert draft.bean_components[0].varietal_names == ["瑰夏"]
    assert draft.bean_components[0].altitude_text == "1800m"


def test_draft_tolerates_missing_or_invalid_bean_fields() -> None:
    assert draft_from_bean_fields({"image_type": "bean_card"}).name is None
    assert draft_from_bean_fields({"bean_fields": "not-a-dict"}).name is None


def test_effective_confidence_takes_min_of_reported_and_assessed() -> None:
    full = _data(
        name="A",
        roaster_name="B",
        bean_components=[{"origin_name": "C", "process_name": "D", "varietal_names": ["E"]}],
    )
    draft = draft_from_bean_fields(full)
    # 字段全齐 assessed=1.0；vision 自报 0.7 → 取 min
    assert effective_confidence({**full, "confidence": 0.7}, draft) == 0.7
    # vision 自报过高也压不过完整度评估
    sparse_draft = draft_from_bean_fields(_data(name="A"))
    assert effective_confidence({**_data(name="A"), "confidence": 0.99}, sparse_draft) == 0.25
    # 自报缺失/非法 → 用完整度评估
    assert effective_confidence(full, draft) == 1.0
    assert effective_confidence({**full, "confidence": 5}, draft) == 1.0


def test_summarize_draft_lists_only_recognized_fields() -> None:
    draft = draft_from_bean_fields(_data(name="瑰夏", origin_name="巴拿马"))
    summary = summarize_draft(draft)
    assert "瑰夏" in summary and "产地 巴拿马" in summary
    assert "烘焙商" not in summary
    assert summarize_draft(draft_from_bean_fields(_data())) == "（没有识别出可用的豆卡信息）"


def test_ocr_raw_input_joins_lines() -> None:
    assert ocr_raw_input({"ocr_text": ["ALD SKY", " PROJECT ", ""]}) == "ALD SKY\nPROJECT"
    assert ocr_raw_input({"ocr_text": []}) is None
    assert ocr_raw_input({}) is None
