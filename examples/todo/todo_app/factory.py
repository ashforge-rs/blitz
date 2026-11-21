"""The application's composition root: the one module that sees every context."""

from typing import TYPE_CHECKING, Any

from app import HealthCheckFn, create_app
from config import get_settings
from state import get_domain

from .auth import BearerTokenAuthProvider, TokenVerifier
from .settings import EXTRA_KEY, TodoSettings
from .todos import domain as todos_domain
from .todos.container import TodosDomain
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
    todo_settings = todo_settings or TodoSettings()
    app = create_app(
        settings=settings or get_settings(),
        auth_provider=BearerTokenAuthProvider(verifier_for=_token_verifier),
        domains=DOMAINS,
        extra_context={EXTRA_KEY: todo_settings},
        **create_app_kwargs,
    )
    # Appended after create_app(): the checks look the domains up once they're bootstrapped.
    app.state.health_checks.extend(_health_checks(app, todo_settings.OUTBOX_MAX_AGE_SECONDS))
    return app


def _health_checks(app: FastAPI, max_outbox_age_s: float) -> list[HealthCheckFn]:
    def check(kind: type[UsersDomain | TodosDomain], name: str) -> HealthCheckFn:
        async def _check() -> dict[str, Any]:
            domain: UsersDomain | TodosDomain | None = app.state.domains_by_type.get(kind)
            if domain is None:
                return {"name": name, "healthy": False, "database": "not started"}
            return dict(await domain.health(max_outbox_age_s=max_outbox_age_s))

        _check.__name__ = name
        return _check

    return [check(UsersDomain, "users"), check(TodosDomain, "todos")]
