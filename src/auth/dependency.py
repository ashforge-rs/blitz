from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from context import RequestContext


def _get_ctx(request: Request) -> RequestContext:
    return request.state.ctx


async def get_auth_context(
    request: Request,
    ctx: Annotated[RequestContext, Depends(_get_ctx)],
) -> Any:
    """
    FastAPI dependency that runs the registered ``AuthProvider``.

    - Calls ``authenticate()``; raises 401 if it returns ``None``.
    - Calls ``authorize()``; raises 403 if it returns ``False``.
    - Stores the resolved principal on ``ctx`` under the key ``"principal"``.
    - Is a no-op (returns ``None``) when no ``auth_provider`` is registered.

    Usage::

        from fastapi import Depends
        from auth.dependency import get_auth_context

        @router.get("/protected")
        async def handler(principal=Depends(get_auth_context)):
            ...
    """
    auth_provider = getattr(request.app.state, "auth_provider", None)
    if auth_provider is None:
        return None

    principal = await auth_provider.authenticate(request)
    if principal is None:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )

    authorized = await auth_provider.authorize(request, principal, ctx)
    if not authorized:
        raise HTTPException(status_code=403, detail="Forbidden")

    ctx.set("principal", principal)
    return principal
