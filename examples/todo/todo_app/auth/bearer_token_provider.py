from typing import TYPE_CHECKING, Any

from context import RequestContext
from deps import get_request_context
from fastapi import Request
from metrics import counter

from todo_app.web import request_actor

from .principal import Principal

if TYPE_CHECKING:
    from collections.abc import Callable

    from .token_verifier import TokenVerifier

#: result: success | missing | invalid | error
AUTH_ATTEMPTS = counter(
    "todoapp_auth_attempts_total",
    "API token authentication attempts, by outcome",
    ["result"],
)


class BearerTokenAuthProvider:
    """blitz ``AuthProvider`` for ``Authorization: Bearer <api token>``."""

    def __init__(self, verifier_for: Callable[[Request], TokenVerifier]) -> None:
        # A lookup, not an instance: the verifier is built in bootstrap(),
        # after the provider is handed to create_app().
        self._verifier_for = verifier_for

    async def authenticate(self, request: Request) -> Principal | None:
        """Return the caller, or ``None`` (→ 401) when the token is missing or unknown."""
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            AUTH_ATTEMPTS.labels(result="missing").inc()
            return None
        try:
            actor = request_actor(get_request_context(request))
            user_id = await self._verifier_for(request).verify(token.strip(), actor)
        except Exception:
            AUTH_ATTEMPTS.labels(result="error").inc()
            raise
        if user_id is None:
            AUTH_ATTEMPTS.labels(result="invalid").inc()
            return None
        AUTH_ATTEMPTS.labels(result="success").inc()
        return Principal(user_id=user_id)

    async def authorize(self, request: Request, principal: Any, context: RequestContext) -> bool:
        # Any registered user may call the API; data access is scoped to the
        # principal inside each use case.
        return isinstance(principal, Principal)
