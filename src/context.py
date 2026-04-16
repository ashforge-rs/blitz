from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from starlette.requests import Request


class RequestContext:
    """
    Per-request context object.

    Attached to every request as ``request.state.ctx``.

    Attributes:
        _request:    The raw Starlette/FastAPI ``Request`` object.
        request_id:  X-Request-ID header value, or a generated UUID4 hex string.

    Usage::

        ctx = request.state.ctx
        ctx.set("user_id", 42)
        ctx.get("user_id")       # 42
        ctx._request.headers     # original request headers
    """

    __slots__ = ("_props", "_request", "_request_id")

    def __init__(self, request: Request, request_id: str = "") -> None:
        self._request: Request = request
        self._request_id: str = request_id
        self._props: dict[str, Any] = {}

    @property
    def request_id(self) -> str:
        return self._request_id

    @property
    def remote_addr(self) -> str | None:
        """IP:port of the connecting client, or None for non-TCP connections."""
        client = self._request.client
        if client is None:
            return None
        return f"{client.host}:{client.port}"

    @property
    def path(self) -> str:
        """URL path of the current request."""
        return str(self._request.url.path)

    def set(self, key: str, value: Any) -> None:
        """Store an arbitrary value on the context."""
        self._props[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value previously stored with :meth:`set`."""
        return self._props.get(key, default)


# Module-level ContextVar — set by RequestContextMiddleware for each request.
# Prefer ``request.state.ctx`` in FastAPI route handlers; use this for
# utility code that has no access to the request object.
_ctx_var: ContextVar[RequestContext] = ContextVar("blitz_request_context")


def get_context() -> RequestContext:
    """Return the current request's context from the active ContextVar.

    Raises ``LookupError`` if called outside of a request context.
    """
    return _ctx_var.get()
