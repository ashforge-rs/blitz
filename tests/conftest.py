from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app import create_app
from audit.backends.noop import NoopAuditBackend
from config import Settings
from services.api.domains import DOMAINS

_TEST_SETTINGS: dict[str, Any] = {
    "ENVIRONMENT": "test",
    "LOG_LEVEL": "WARNING",
    "RATE_LIMIT": "1000/minute",
    "METRICS_ENDPOINT_ENABLED": True,
    "METRICS_REQUIRE_AUTH": False,
}


@pytest.fixture
def make_settings() -> Callable[..., Settings]:
    """``make_settings(RATE_LIMIT="1/minute")`` → test Settings with overrides.

    A developer's local ``.env`` is never read, so results don't depend on it.
    """

    def _make(**overrides: Any) -> Settings:
        return Settings(_env_file=None, **(_TEST_SETTINGS | overrides))  # type: ignore[call-arg]

    return _make


@pytest.fixture
def test_settings(make_settings) -> Settings:
    return make_settings()


@pytest.fixture
def make_app(make_settings) -> Callable[..., FastAPI]:
    """``make_app(settings={"ENVIRONMENT": "production"}, health_checks=[...])``.

    ``settings`` may be a ``Settings`` or a mapping of overrides on the test
    defaults; other keyword arguments go to ``create_app()``.  The audit backend
    defaults to a no-op and no domains are registered unless passed.
    """

    def _make(*, settings: Settings | Mapping[str, Any] | None = None, **kwargs: Any) -> FastAPI:
        if not isinstance(settings, Settings):
            settings = make_settings(**(settings or {}))
        kwargs.setdefault("audit_backend", NoopAuditBackend())
        return create_app(settings=settings, **kwargs)

    return _make


@pytest.fixture
def make_client() -> Callable[..., Any]:
    """``async with make_client(app) as c:`` — HTTP client with the app's lifespan running.

    Pass ``raise_app_exceptions=False`` to inspect 500 responses instead of
    having the exception re-raised into the test.
    """

    @asynccontextmanager
    async def _make(
        app: FastAPI, *, lifespan: bool = True, raise_app_exceptions: bool = True
    ) -> AsyncIterator[AsyncClient]:
        async with AsyncExitStack() as stack:
            if lifespan:
                await stack.enter_async_context(LifespanManager(app))
            transport = ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
            yield await stack.enter_async_context(
                AsyncClient(transport=transport, base_url="http://test")
            )

    return _make


@pytest.fixture
def app(make_app) -> FastAPI:
    """The app with every domain the ``api`` service serves."""
    return make_app(domains=DOMAINS)


@pytest.fixture
async def client(app, make_client) -> AsyncIterator[AsyncClient]:
    async with make_client(app) as c:
        yield c
