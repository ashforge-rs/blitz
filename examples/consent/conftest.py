"""Shared fixtures for every test tier."""

from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
from asgi_lifespan import LifespanManager
from config import Settings
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from prometheus_client import REGISTRY
from pydantic import SecretStr

from consent_app.adapters.api_keys import generate_key, hash_key
from consent_app.adapters.sql.database import Database
from consent_app.factory import create_consent_app
from consent_app.settings import ConsentSettings
from consent_tests.fakes import RecordingAuditBackend
from consent_tests.storage import BACKENDS, open_migrated, url_for


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "consent.db")


@pytest.fixture
def database_url(db_path: str) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


@pytest.fixture(params=BACKENDS)
async def backend_url(request: pytest.FixtureRequest, database_url: str) -> str:
    """An empty database on each configured backend (see ``consent_tests/storage.py``)."""
    return await url_for(request.param, database_url)


@pytest.fixture
async def db(backend_url: str) -> AsyncIterator[Database]:
    database = await open_migrated(backend_url)
    yield database
    await database.close()


@pytest.fixture
def api_key() -> str:
    return generate_key()


@pytest.fixture
def audit_log() -> RecordingAuditBackend:
    return RecordingAuditBackend()


@pytest.fixture
def consent_settings(database_url: str, api_key: str) -> ConsentSettings:
    return ConsentSettings(  # type: ignore[call-arg]  # pydantic-settings init kwarg
        _env_file=None,
        DATABASE_URL=SecretStr(database_url),
        API_KEYS=SecretStr(f"tests={hash_key(api_key)},other=" + "0" * 64),
    )


@pytest.fixture
def app(consent_settings: ConsentSettings, audit_log: RecordingAuditBackend) -> FastAPI:
    settings = Settings(  # type: ignore[call-arg]  # pydantic-settings init kwarg
        _env_file=None, ENVIRONMENT="test", LOG_LEVEL="WARNING", RATE_LIMIT="1000/minute"
    )
    return create_consent_app(
        settings=settings, consent_settings=consent_settings, audit_backend=audit_log
    )


@pytest.fixture
async def anonymous(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A client with no API key."""
    async with LifespanManager(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
def client(anonymous: AsyncClient, api_key: str) -> AsyncClient:
    """The ``tests`` client system, authenticated."""
    anonymous.headers["Authorization"] = f"Bearer {api_key}"
    return anonymous


@pytest.fixture
def metric() -> Callable[..., float]:
    """``metric(name, **labels)`` → the sample's current value (0 if unset)."""

    def _value(name: str, **labels: str) -> float:
        return REGISTRY.get_sample_value(name, labels) or 0.0

    return _value
