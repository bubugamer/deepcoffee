from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401  (register models on Base.metadata)
from app.core import db as db_module
from app.core.db import Base
from app.services.billing_service import billing_service as _billing_service

# 测试里禁用 new-api：endpoint 不应去连真 new-api 建影子账户、污染它。
_billing_service.settings.new_api_base_url = None
# 测试里禁用 Sentry：create_app 的 init_observability 不应把测试中的错误上报到真 Sentry。
# settings 是全局单例（与 create_app 里 init_observability 读的是同一个对象），这里清掉即不初始化。
_billing_service.settings.sentry_dsn = None
# 测试默认关掉邀请门禁（业务端点的测试用户没有绑定邀请码）；
# 门禁本身的行为由 test_invite_gate.py 显式开启后覆盖。
_billing_service.settings.enforce_invite_gate = False
# 测试固定跑在 local 语义下（接受 dev token），不随 .env 的 APP_ENV 漂移——
# 本地模拟生产部署时 .env 会切到 production，测试不应因此全挂。
_billing_service.settings.app_env = "local"
# 同理，测试不读 .env 里的 bootstrap 码（test_quota_and_admin 用自己设的码）。
_billing_service.settings.bootstrap_invite_code = None

TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://deepcoffee:deepcoffee@localhost:5433/deepcoffee_test",
)

# Replace the app's global engine/sessionmaker with one bound to the isolated test
# database. Done explicitly (not via env vars) so it cannot fall back to the dev DB.
# NullPool: the sync TestClient drives the async app across event loops, so we must
# not reuse asyncpg connections bound to a different loop.
_test_engine = create_async_engine(TEST_URL, poolclass=NullPool)
db_module._engine = _test_engine
db_module._sessionmaker = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def _db_schema():
    async def _create() -> None:
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    yield
    asyncio.run(_test_engine.dispose())


@pytest.fixture(autouse=True)
def _clean_tables():
    async def _truncate() -> None:
        async with _test_engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))

    asyncio.run(_truncate())
    yield
