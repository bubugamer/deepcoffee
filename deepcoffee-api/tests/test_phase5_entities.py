from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

ADMIN = {"Authorization": "Bearer dev:admin-1:admin@example.com"}
USER = {"Authorization": "Bearer dev:bean-fact-user:user@example.com"}


def test_proposal_approve_materializes_public_entity() -> None:
    client = TestClient(create_app())
    created = client.post(
        "/v1/proposals",
        headers=ADMIN,
        json={
            "entity_type": "roaster",
            "title": "Add Seesaw",
            "payload": {"name": "Seesaw 咖啡", "country": "中国", "region": "上海"},
        },
    )
    proposal_id = created.json()["proposal_id"]

    approved = client.post(
        f"/v1/admin/proposals/{proposal_id}/approve", headers=ADMIN, json={"reviewer_note": "ok"}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    # 批准即进入公共实体库，记下 applied_entity_id。
    assert approved.json()["applied_entity_id"]

    entities = client.get("/v1/admin/entities", headers=ADMIN, params={"entity_type": "roaster"})
    assert entities.status_code == 200
    assert any(e["canonical_name"] == "Seesaw 咖啡" for e in entities.json())

    # mark-applied 跑知识库同步管线并记 markdown 路径。
    applied = client.post(
        f"/v1/admin/proposals/{proposal_id}/mark-applied",
        headers=ADMIN,
        json={"applied_markdown_path": "roasters/seesaw.md"},
    )
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert applied.json()["applied_markdown_path"] == "roasters/seesaw.md"
    # 幂等：applied_entity_id 与批准时一致。
    assert applied.json()["applied_entity_id"] == approved.json()["applied_entity_id"]


def test_bean_confirm_generates_candidate_facts_for_public_entities() -> None:
    client = TestClient(create_app())
    confirmed = client.post(
        "/v1/beans/confirm",
        headers=USER,
        json={
            "draft": {
                "name": "花魁 5.0",
                "roaster_name": "鹰集",
                "origin_name": "埃塞俄比亚",
                "process_name": "日晒",
                "varietal_names": ["原生种"],
                "private_notes": "我觉得这支适合中度烘焙，个人很爱（主观，不应成为候选）",
            }
        },
    )
    assert confirmed.status_code == 200, confirmed.text

    candidates = client.get("/v1/admin/candidates", headers=ADMIN)
    assert candidates.status_code == 200
    titles = {c["title"] for c in candidates.json()}
    types = {c["entity_type"] for c in candidates.json()}
    # 客观公共实体事实进候选。
    assert "鹰集" in titles
    assert "埃塞俄比亚" in titles
    assert "日晒" in titles
    assert "原生种" in titles
    assert "roaster" in types and "process_method" in types
    # 主观备注不会变成候选。
    assert all("中度烘焙" not in c["title"] for c in candidates.json())


def test_candidate_promote_to_proposal_then_into_entity_library() -> None:
    client = TestClient(create_app())
    client.post(
        "/v1/beans/confirm",
        headers=USER,
        json={
            "draft": {
                "name": "瑰夏红标",
                "roaster_name": "翡翠庄园",
                "origin_name": "巴拿马",
                "process_name": "水洗",
                "varietal_names": ["瑰夏"],
            }
        },
    )
    candidates = client.get("/v1/admin/candidates", headers=ADMIN, params={"entity_type": "roaster"})
    roaster_candidate = next(c for c in candidates.json() if c["title"] == "翡翠庄园")

    promoted = client.post(
        f"/v1/admin/candidates/{roaster_candidate['id']}/promote", headers=ADMIN, json={}
    )
    assert promoted.status_code == 200, promoted.text
    proposal_id = promoted.json()["proposal_id"]
    assert promoted.json()["status"] == "promoted"

    # 候选已标记 promoted 并关联 proposal。
    detail = client.get(f"/v1/admin/candidates/{roaster_candidate['id']}", headers=ADMIN)
    assert detail.json()["status"] == "promoted"
    assert detail.json()["proposal_id"] == proposal_id

    # 提案批准 → 进入公共实体库。
    approved = client.post(
        f"/v1/admin/proposals/{proposal_id}/approve", headers=ADMIN, json={}
    )
    assert approved.json()["applied_entity_id"]
    entities = client.get("/v1/admin/entities", headers=ADMIN, params={"entity_type": "roaster"})
    assert any(e["canonical_name"] == "翡翠庄园" for e in entities.json())


def test_existing_entity_suppresses_duplicate_candidate() -> None:
    client = TestClient(create_app())
    # 先让「水洗」处理法进公共实体库。
    created = client.post(
        "/v1/proposals",
        headers=ADMIN,
        json={"entity_type": "process_method", "title": "水洗", "payload": {"name": "水洗"}},
    )
    client.post(
        f"/v1/admin/proposals/{created.json()['proposal_id']}/approve", headers=ADMIN, json={}
    )

    # 用户建一支「水洗」豆卡：已存在 active 实体 → 不再为「水洗」生成候选。
    client.post(
        "/v1/beans/confirm",
        headers=USER,
        json={"draft": {"name": "水洗测试豆", "roaster_name": "测试烘焙", "origin_name": "巴拿马", "process_name": "水洗"}},
    )
    process_candidates = client.get(
        "/v1/admin/candidates", headers=ADMIN, params={"entity_type": "process_method"}
    )
    assert all(c["title"] != "水洗" for c in process_candidates.json())


def test_candidate_reject() -> None:
    client = TestClient(create_app())
    client.post(
        "/v1/beans/confirm",
        headers=USER,
        json={"draft": {"name": "拒绝测试豆", "roaster_name": "某不知名烘焙商X", "origin_name": "巴拿马", "process_name": "水洗"}},
    )
    candidates = client.get("/v1/admin/candidates", headers=ADMIN, params={"entity_type": "roaster"})
    target = next(c for c in candidates.json() if c["title"] == "某不知名烘焙商X")
    rejected = client.post(
        f"/v1/admin/candidates/{target['id']}/reject", headers=ADMIN, json={"reviewer_note": "无法核实"}
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
