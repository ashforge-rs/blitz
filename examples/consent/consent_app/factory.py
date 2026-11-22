from typing import TYPE_CHECKING, Any

from app import create_app
from config import get_settings

from . import domain
from .adapters.api_keys import parse_api_keys
from .adapters.auth import ApiKeyAuthProvider
from .container import ConsentDomain
from .settings import EXTRA_KEY, ConsentSettings

if TYPE_CHECKING:
    from config import Settings
    from fastapi import FastAPI


def create_consent_app(
    *,
    settings: Settings | None = None,
    consent_settings: ConsentSettings | None = None,
    **create_app_kwargs: Any,
) -> FastAPI:
    """``create_app()`` with the consent domain, API-key auth and a database health check."""
    consent_settings = consent_settings or ConsentSettings()
    keys = parse_api_keys(consent_settings.API_KEYS.get_secret_value())
    app = create_app(
        settings=settings or get_settings(),
        auth_provider=ApiKeyAuthProvider(keys),
        domains=[domain],
        extra_context={EXTRA_KEY: consent_settings},
        **create_app_kwargs,
    )

    async def consent_store() -> dict[str, Any]:
        found: ConsentDomain | None = app.state.domains_by_type.get(ConsentDomain)
        healthy = found is not None and await found.db.ping()
        return {"name": "consent_store", "healthy": healthy, "profile": consent_settings.PROFILE}

    app.state.health_checks.append(consent_store)
    return app
