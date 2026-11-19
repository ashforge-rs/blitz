from typing import Annotated

from fastapi import Depends, Request

from audit.backend import AuditBackend, AuditIntegrity
from context import RequestContext
from state import get_domain

from .service import ItemService


def _get_item_service(request: Request) -> ItemService:
    # Imported lazily: domain.py imports this module, so a top-level import
    # would be circular.
    from .domain import ItemsDomain

    return get_domain(request, ItemsDomain).service


def _get_ctx(request: Request) -> RequestContext:
    ctx = request.state.ctx
    if not isinstance(ctx, RequestContext):
        msg = "request.state.ctx is missing — is RequestContextMiddleware installed?"
        raise TypeError(msg)
    return ctx


def _get_audit_backend(request: Request) -> AuditBackend:
    backend = request.app.state.audit_backend
    if not isinstance(backend, AuditBackend):
        msg = f"app.state.audit_backend is {type(backend).__name__}, expected AuditBackend"
        raise TypeError(msg)
    return backend


def _get_audit_integrity(request: Request) -> AuditIntegrity:
    integrity = request.app.state.audit_integrity
    if not isinstance(integrity, AuditIntegrity):
        msg = f"app.state.audit_integrity is {type(integrity).__name__}, expected AuditIntegrity"
        raise TypeError(msg)
    return integrity


ItemServiceDep = Annotated[ItemService, Depends(_get_item_service)]
RequestContextDep = Annotated[RequestContext, Depends(_get_ctx)]
AuditBackendDep = Annotated[AuditBackend, Depends(_get_audit_backend)]
AuditIntegrityDep = Annotated[AuditIntegrity, Depends(_get_audit_integrity)]
