from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from context import RequestContext

from .service import ItemService


def _get_item_service(request: Request) -> ItemService:
    domain = request.app.state.domains["example.domain"]
    return domain.service


def _get_ctx(request: Request) -> RequestContext:
    return request.state.ctx


ItemServiceDep = Annotated[ItemService, Depends(_get_item_service)]
RequestContextDep = Annotated[RequestContext, Depends(_get_ctx)]
