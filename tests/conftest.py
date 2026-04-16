from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app import create_app
from audit.backends.noop import NoopAuditBackend
from config import Settings
from example import domain as example_domain


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        ENVIRONMENT="test",
        LOG_LEVEL="WARNING",
        RATE_LIMIT="1000/minute",
        METRICS_ENDPOINT_ENABLED=True,
        METRICS_REQUIRE_AUTH=False,
    )


@pytest.fixture
def app(test_settings):
    return create_app(
        settings=test_settings,
        audit_backend=NoopAuditBackend(),
        domains=[example_domain],
    )


@pytest.fixture
async def client(app):
    async with (
        LifespanManager(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c,
    ):
        yield c
