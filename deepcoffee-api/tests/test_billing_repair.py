from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import admin as admin_module
from app.core.db import get_sessionmaker
from app.main import create_app
from app.models.tables import NewapiBillingLink, UserProfile
from app.services.billing_service import billing_service
from app.services.newapi_client import NewApiError

ADMIN_HEADERS = {"Authorization": "Bearer dev:admin-1:admin@example.com"}
USER_HEADERS = {"Authorization": "Bearer dev:user-1:user@example.com"}


@pytest.fixture(autouse=True)
def _restore_billing_settings() -> Iterator[None]:
    settings = billing_service.settings
    original = {
        "new_api_base_url": settings.new_api_base_url,
        "new_api_admin_token": settings.new_api_admin_token,
        "admin_user_ids": list(settings.admin_user_ids),
    }
    yield
    settings.new_api_base_url = original["new_api_base_url"]
    settings.new_api_admin_token = original["new_api_admin_token"]
    settings.admin_user_ids = original["admin_user_ids"]


def _enable_new_api() -> None:
    billing_service.settings.new_api_base_url = "http://new-api.test"
    billing_service.settings.new_api_admin_token = "admin-token"


async def _seed_profile(
    user_id: str = "user-1", *, email: str = "user@example.com", plan: str = "basic"
) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        session.add(UserProfile(id=user_id, email=email, plan=plan))
        await session.commit()


async def _seed_profile_and_link(
    user_id: str = "user-1",
    *,
    email: str = "user@example.com",
    plan: str = "basic",
    newapi_user_id: str = "old-newapi-user",
    token: str | None = "sk-old",
) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        session.add(UserProfile(id=user_id, email=email, plan=plan))
        await session.flush()
        session.add(
            NewapiBillingLink(
                user_id=user_id,
                newapi_user_id=newapi_user_id,
                internal_token=token,
                plan=plan,
                last_synced_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _read_link(user_id: str = "user-1") -> tuple[str, str | None] | None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        link = await session.get(NewapiBillingLink, user_id)
        if link is None:
            return None
        return link.newapi_user_id, link.internal_token


def _fake_ensure_shadow_account(newapi_user_id: str = "new-newapi-user", token: str | None = "sk-new"):
    async def _ensure(
        session: AsyncSession, user_id: str, email: str | None = None, plan: str = "basic"
    ) -> NewapiBillingLink:
        existing = await session.get(NewapiBillingLink, user_id)
        if existing is not None:
            return existing
        link = NewapiBillingLink(
            user_id=user_id,
            newapi_user_id=newapi_user_id,
            internal_token=token,
            plan=plan,
            last_synced_at=datetime.now(timezone.utc),
        )
        session.add(link)
        await session.flush()
        return link

    return _ensure


def test_repair_skips_when_new_api_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_seed_profile_and_link())
    billing_service.settings.new_api_base_url = None
    billing_service.settings.new_api_admin_token = None
    monkeypatch.setattr(
        billing_service,
        "ensure_shadow_account",
        pytest.fail,
    )

    response = TestClient(create_app()).post("/v1/admin/billing-links/user-1/repair", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "status": "skipped",
        "reason": "new-api is not configured",
        "old_newapi_user_id": None,
        "newapi_user_id": None,
        "has_token": False,
    }
    assert asyncio.run(_read_link()) == ("old-newapi-user", "sk-old")


def test_repair_requires_admin_when_admins_are_configured() -> None:
    billing_service.settings.admin_user_ids = ["admin-1"]

    response = TestClient(create_app()).post("/v1/admin/billing-links/user-1/repair", headers=USER_HEADERS)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_required"


def test_repair_recreates_link_after_remote_delete_success(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_seed_profile_and_link(newapi_user_id="remote-old"))
    _enable_new_api()
    deleted: list[str] = []

    class FakeNewApiClient:
        def __init__(self, settings) -> None:
            self.settings = settings

        async def delete_user(self, newapi_user_id: str) -> None:
            deleted.append(newapi_user_id)

    monkeypatch.setattr(admin_module, "NewApiClient", FakeNewApiClient)
    monkeypatch.setattr(billing_service, "ensure_shadow_account", _fake_ensure_shadow_account("remote-new", "sk-new"))

    response = TestClient(create_app()).post("/v1/admin/billing-links/user-1/repair", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "status": "repaired",
        "reason": None,
        "old_newapi_user_id": "remote-old",
        "newapi_user_id": "remote-new",
        "has_token": True,
    }
    assert deleted == ["remote-old"]
    assert asyncio.run(_read_link()) == ("remote-new", "sk-new")


def test_repair_recreates_link_when_remote_user_is_already_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_seed_profile_and_link(newapi_user_id="remote-missing"))
    _enable_new_api()

    class FakeNewApiClient:
        def __init__(self, settings) -> None:
            self.settings = settings

        async def delete_user(self, newapi_user_id: str) -> None:
            raise NewApiError("record not found")

    monkeypatch.setattr(admin_module, "NewApiClient", FakeNewApiClient)
    monkeypatch.setattr(billing_service, "ensure_shadow_account", _fake_ensure_shadow_account("remote-new", "sk-new"))

    response = TestClient(create_app()).post("/v1/admin/billing-links/user-1/repair", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json()["status"] == "repaired"
    assert response.json()["newapi_user_id"] == "remote-new"
    assert asyncio.run(_read_link()) == ("remote-new", "sk-new")


def test_repair_keeps_local_link_when_remote_delete_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_seed_profile_and_link(newapi_user_id="remote-old"))
    _enable_new_api()

    class FakeNewApiClient:
        def __init__(self, settings) -> None:
            self.settings = settings

        async def delete_user(self, newapi_user_id: str) -> None:
            raise NewApiError("new-api unreachable", status_code=503)

    async def fail_ensure(*args, **kwargs):
        pytest.fail("repair must not recreate a link after remote delete fails")

    monkeypatch.setattr(admin_module, "NewApiClient", FakeNewApiClient)
    monkeypatch.setattr(billing_service, "ensure_shadow_account", fail_ensure)

    response = TestClient(create_app()).post("/v1/admin/billing-links/user-1/repair", headers=ADMIN_HEADERS)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "new_api_delete_failed"
    assert asyncio.run(_read_link()) == ("remote-old", "sk-old")


def test_repair_creates_link_when_local_link_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_seed_profile())
    _enable_new_api()
    deleted: list[str] = []

    class FakeNewApiClient:
        def __init__(self, settings) -> None:
            self.settings = settings

        async def delete_user(self, newapi_user_id: str) -> None:
            deleted.append(newapi_user_id)

    monkeypatch.setattr(admin_module, "NewApiClient", FakeNewApiClient)
    monkeypatch.setattr(billing_service, "ensure_shadow_account", _fake_ensure_shadow_account("remote-new", "sk-new"))

    response = TestClient(create_app()).post("/v1/admin/billing-links/user-1/repair", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "status": "created",
        "reason": None,
        "old_newapi_user_id": None,
        "newapi_user_id": "remote-new",
        "has_token": True,
    }
    assert deleted == []
    assert asyncio.run(_read_link()) == ("remote-new", "sk-new")
