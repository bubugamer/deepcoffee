from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_public_entity_proposal_review_flow() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:admin-1:admin@example.com"}

    created = client.post(
        "/v1/proposals",
        headers=headers,
        json={
            "entity_type": "roaster",
            "title": "Add Test Roaster",
            "payload": {"name": "Test Roaster", "city": "Shanghai"},
            "source_input": "Please add Test Roaster.",
            "trace_id": "trace_123",
        },
    )
    assert created.status_code == 200
    proposal_id = created.json()["proposal_id"]
    assert created.json()["status"] == "pending"

    listed = client.get("/v1/admin/proposals", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == proposal_id for item in listed.json())

    approved = client.post(
        f"/v1/admin/proposals/{proposal_id}/approve",
        headers=headers,
        json={"reviewer_note": "Looks reasonable."},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    applied = client.post(
        f"/v1/admin/proposals/{proposal_id}/mark-applied",
        headers=headers,
        json={"applied_markdown_path": "knowledge/roasters/国际/Test.md"},
    )
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
