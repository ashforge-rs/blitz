"""Bearer API-key authentication of client systems, plugged into blitz's AuthProvider."""

from typing import Annotated, Any

from auth.dependency import get_auth_context
from context import RequestContext
from fastapi import Depends, Request

from .api_keys import hash_key


class ApiKeyAuthProvider:
    """``Authorization: Bearer <key>`` → the client's name, recorded on every event it writes."""

    def __init__(self, keys: dict[str, str]) -> None:
        self._clients_by_hash = keys

    async def authenticate(self, request: Request) -> str | None:
        scheme, _, key = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not key.strip():
            return None
        return self._clients_by_hash.get(hash_key(key.strip()))

    async def authorize(self, request: Request, principal: Any, context: RequestContext) -> bool:
        return isinstance(principal, str)


def _current_client(principal: Annotated[Any, Depends(get_auth_context)]) -> str:
    if not isinstance(principal, str):
        msg = "no authenticated client: build the app with create_consent_app()"
        raise TypeError(msg)
    return principal


#: Route parameter that requires a valid API key (401 otherwise).
CurrentClientDep = Annotated[str, Depends(_current_client)]
