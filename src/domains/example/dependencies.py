from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from audit.backend import AuditBackend, AuditIntegrity
from context import RequestContext

from .service import ItemService


def _get_item_service(request: Request) -> ItemService:
    domain = request.app.state.domains["domains.example.domain"]
    return cast("ItemService", domain.service)


def _get_ctx(request: Request) -> RequestContext:
    return cast("RequestContext", request.state.ctx)


def _get_audit_backend(request: Request) -> AuditBackend:
    return cast("AuditBackend", request.app.state.audit_backend)


def _get_audit_integrity(request: Request) -> AuditIntegrity:
    return cast("AuditIntegrity", request.app.state.audit_integrity)


ItemServiceDep = Annotated[ItemService, Depends(_get_item_service)]
RequestContextDep = Annotated[RequestContext, Depends(_get_ctx)]
AuditBackendDep = Annotated[AuditBackend, Depends(_get_audit_backend)]
AuditIntegrityDep = Annotated[AuditIntegrity, Depends(_get_audit_integrity)]
