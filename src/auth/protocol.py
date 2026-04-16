from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from starlette.requests import Request

from context import RequestContext


@runtime_checkable
class AuthProvider(Protocol):
    """
    Protocol for pluggable authentication and authorisation.

    Implement both methods and pass an instance to ``create_app(auth_provider=...)``.

    Example::

        class JWTAuthProvider:
            async def authenticate(self, request: Request) -> dict | None:
                token = request.headers.get("authorization", "").removeprefix("Bearer ")
                return verify_jwt(token)  # return None to signal unauthenticated

            async def authorize(
                self, request: Request, principal: dict, ctx: RequestContext
            ) -> bool:
                return "read" in principal.get("scopes", [])
    """

    async def authenticate(self, request: Request) -> Any:
        """
        Verify the request credentials and return the resolved principal.

        Return ``None`` to signal that the request is unauthenticated (→ 401).
        Raise ``fastapi.HTTPException`` directly for custom status codes.
        """
        ...

    async def authorize(
        self,
        request: Request,
        principal: Any,
        context: RequestContext,
    ) -> bool:
        """
        Decide whether the authenticated *principal* may proceed.

        Return ``False`` to reject with 403 Forbidden.
        """
        ...
