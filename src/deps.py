"""
Framework-level FastAPI dependencies shared by every domain.

Use the ``Annotated`` aliases directly in route signatures or in a domain's own
``dependencies.py``::

    from deps import RequestContextDep


    @router.get("/")
    async def list_orders(ctx: RequestContextDep) -> list[Order]: ...

Each accessor checks the type of what it reads from ``app.state`` /
``request.state`` so a mis-wired app fails with a clear error, not an
``AttributeError`` deep inside a handler.
"""

from typing import Annotated

from fastapi import Depends, Request

from audit.backend import AuditBackend, AuditIntegrity
from config import Settings
from context import RequestContext


def get_request_context(request: Request) -> RequestContext:
    ctx = getattr(request.state, "ctx", None)
    if not isinstance(ctx, RequestContext):
        msg = "request.state.ctx is missing — is RequestContextMiddleware installed?"
        raise TypeError(msg)
    return ctx


def get_app_settings(request: Request) -> Settings:
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        msg = f"app.state.settings is {type(settings).__name__}, expected Settings"
        raise TypeError(msg)
    return settings


def get_audit_backend(request: Request) -> AuditBackend:
    backend = request.app.state.audit_backend
    if not isinstance(backend, AuditBackend):
        msg = f"app.state.audit_backend is {type(backend).__name__}, expected AuditBackend"
        raise TypeError(msg)
    return backend


def get_audit_integrity(request: Request) -> AuditIntegrity:
    integrity = request.app.state.audit_integrity
    if not isinstance(integrity, AuditIntegrity):
        msg = f"app.state.audit_integrity is {type(integrity).__name__}, expected AuditIntegrity"
        raise TypeError(msg)
    return integrity


RequestContextDep = Annotated[RequestContext, Depends(get_request_context)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
AuditBackendDep = Annotated[AuditBackend, Depends(get_audit_backend)]
AuditIntegrityDep = Annotated[AuditIntegrity, Depends(get_audit_integrity)]
