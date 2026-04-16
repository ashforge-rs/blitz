from __future__ import annotations

import inspect
from collections.abc import Callable  # noqa: TC003 — used at runtime in DomainRouter.add_api_route
from functools import wraps
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from returns.result import Failure, Result, Success

from store.memory import InMemoryStore

from .dependencies import (  # noqa: TC001 — FastAPI resolves Annotated[..., Depends] at runtime via get_type_hints()
    ItemServiceDep,
    RequestContextDep,
)
from .errors import ItemDomainError, ItemError, ItemErrorCode
from .models import CreateItemRequest, Item, UpdateItemRequest
from .repository import ItemRepository
from .service import ItemService

if TYPE_CHECKING:
    from fastapi import FastAPI

    from audit.backend import AuditBackend, AuditIntegrity
    from config import Settings

# ---------------------------------------------------------------------------
# Domain container
# ---------------------------------------------------------------------------


class ItemsDomain:
    """Holds bootstrapped service instances for the *example* bounded context."""

    def __init__(self, service: ItemService) -> None:
        self.service = service


# ---------------------------------------------------------------------------
# Domain exception handler — single place that maps ItemError → HTTP.
#
# Registered via register_exception_handlers(app), called by app.py for every
# domain module that exposes it.  Equivalent to a Gin error middleware: it runs
# after the handler and translates domain errors into responses.
# ---------------------------------------------------------------------------


async def _item_error_handler(request: Request, exc: ItemDomainError) -> JSONResponse:
    """Convert ItemDomainError to the appropriate HTTP JSON response."""
    match exc.error.code:
        case ItemErrorCode.NOT_FOUND:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"detail": exc.error.message},
            )
        case ItemErrorCode.CONFLICT:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": exc.error.message},
            )
        case ItemErrorCode.STORAGE_ERROR:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Storage error"},
            )


def register_exception_handlers(app: FastAPI) -> None:
    """Register domain-scoped exception handlers on the FastAPI app.

    Called automatically by ``create_app()`` for every domain module that
    exposes this function.  Equivalent to ``r.Use(errorMiddleware)`` in Gin.
    """
    app.add_exception_handler(ItemDomainError, _item_error_handler)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# DomainRouter — intercepts Result return values at the routing layer.
#
# Every handler registered on this router is automatically wrapped: if the
# handler returns a Result, Success is unwrapped to its inner value and
# Failure raises ItemDomainError (caught by the exception handler above).
# Handlers that return a plain value or None pass through unmodified.
#
# FastAPI resolves dependencies from the original function's __signature__,
# which is explicitly preserved on the wrapper so DI works correctly.
# ---------------------------------------------------------------------------


class DomainRouter(APIRouter):
    """APIRouter that transparently unwraps Result return values."""

    def add_api_route(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        @wraps(endpoint)
        async def _wrapper(*args: Any, **kw: Any) -> Any:
            rv = await endpoint(*args, **kw)
            match rv:
                case Success(v):
                    return v
                case Failure(e):
                    raise ItemDomainError(e)
                case _:
                    return rv

        # Preserve the original signature so FastAPI resolves Depends() correctly.
        _wrapper.__signature__ = inspect.signature(endpoint)  # type: ignore[attr-defined]
        super().add_api_route(path, _wrapper, **kwargs)


# ---------------------------------------------------------------------------
# Gin-style endpoint group — pure service delegates, zero error-handling logic.
# ---------------------------------------------------------------------------


class ItemEndpoints:
    def __init__(self, service: ItemServiceDep, ctx: RequestContextDep) -> None:
        self._svc = service
        self._ctx = ctx

    async def list_items(self) -> Result[list[Item], ItemError]:
        return await self._svc.list_all(self._ctx)

    async def create_item(self, body: CreateItemRequest) -> Result[Item, ItemError]:
        return await self._svc.create(body, self._ctx)

    async def get_item(self, item_id: str) -> Result[Item, ItemError]:
        return await self._svc.get(item_id, self._ctx)

    async def update_item(self, item_id: str, body: UpdateItemRequest) -> Result[Item, ItemError]:
        return await self._svc.update(item_id, body, self._ctx)

    async def delete_item(self, item_id: str) -> Result[None, ItemError]:
        return await self._svc.delete(item_id, self._ctx)


ItemEndpointsDep = Annotated[ItemEndpoints, Depends(ItemEndpoints)]

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_router = DomainRouter(prefix="/example", tags=["example"])


@_router.get("/", response_model=list[Item])
async def list_items(ep: ItemEndpointsDep) -> Result[list[Item], ItemError]:
    return await ep.list_items()


@_router.post("/", response_model=Item, status_code=status.HTTP_201_CREATED)
async def create_item(body: CreateItemRequest, ep: ItemEndpointsDep) -> Result[Item, ItemError]:
    return await ep.create_item(body)


@_router.get("/{item_id}", response_model=Item)
async def get_item(item_id: str, ep: ItemEndpointsDep) -> Result[Item, ItemError]:
    return await ep.get_item(item_id)


@_router.patch("/{item_id}", response_model=Item)
async def update_item(
    item_id: str, body: UpdateItemRequest, ep: ItemEndpointsDep
) -> Result[Item, ItemError]:
    return await ep.update_item(item_id, body)


@_router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_item(item_id: str, ep: ItemEndpointsDep) -> Result[None, ItemError]:
    return await ep.delete_item(item_id)


def make_router() -> APIRouter:
    return _router


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


async def bootstrap(settings: Settings, **kwargs: Any) -> ItemsDomain:
    """
    Wires together the storage, repository, and service for the items domain.

    Receives ``audit_backend`` and ``audit_integrity`` from the framework
    lifespan via ``**kwargs`` so the service can emit structured audit events
    without reaching back into ``app.state`` (Dependency Inversion Principle).

    To swap the storage backend: replace ``InMemoryStore()`` with any class
    that satisfies the ``KeyValueStore`` protocol (e.g. a Redis-backed store).
    Nothing else in this module — or in the service/repository layers — needs
    to change.
    """
    from audit.backends.noop import NoopAuditBackend
    from audit.integrity import NoIntegrity

    audit_backend: AuditBackend = kwargs.get("audit_backend") or NoopAuditBackend()
    audit_integrity: AuditIntegrity = kwargs.get("audit_integrity") or NoIntegrity()

    store: InMemoryStore[str, Item] = InMemoryStore()
    repository = ItemRepository(store=store)
    service = ItemService(
        repository=repository,
        audit_backend=audit_backend,
        audit_integrity=audit_integrity,
    )
    return ItemsDomain(service=service)
