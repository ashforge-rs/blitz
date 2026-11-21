"""The application's composition root: the one module that sees every context."""

from typing import TYPE_CHECKING, Any

from app import create_app
from config import get_settings
from state import get_domain

from .auth import BearerTokenAuthProvider, TokenVerifier
from .settings import EXTRA_KEY, TodoSettings
from .todos import domain as todos_domain
from .users import domain as users_domain
from .users.adapters.users_token_verifier import UsersTokenVerifier
from .users.container import UsersDomain

if TYPE_CHECKING:
    import types

    from config import Settings
    from fastapi import FastAPI, Request

DOMAINS: list[types.ModuleType] = [users_domain, todos_domain]


def _token_verifier(request: Request) -> TokenVerifier:
    return UsersTokenVerifier(get_domain(request, UsersDomain).authenticate)


def create_todo_app(
    *,
    settings: Settings | None = None,
    todo_settings: TodoSettings | None = None,
    **create_app_kwargs: Any,
) -> FastAPI:
    """``create_app()`` with this app's domains, auth provider and settings.

    Extra keyword arguments (``audit_backend``, ``health_checks``, ...) go to
    ``create_app()`` unchanged.
    """
    return create_app(
        settings=settings or get_settings(),
        auth_provider=BearerTokenAuthProvider(verifier_for=_token_verifier),
        domains=DOMAINS,
        extra_context={EXTRA_KEY: todo_settings or TodoSettings()},
        **create_app_kwargs,
    )
