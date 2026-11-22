from typing import TYPE_CHECKING

from fastapi import APIRouter, status
from returns.result import Result

from deps import RequestContextDep
from routing import ResultRouter
from store.memory import InMemoryStore

from .dependencies import ItemServiceDep
from .errors import ItemError
from .models import CreateItemRequest, Item, UpdateItemRequest
from .repository import ItemRepository
from .service import ItemService

if TYPE_CHECKING:
    from bootstrap import BootstrapContext

# ---------------------------------------------------------------------------
# Domain container — what bootstrap() returns and get_domain() looks up.
# ---------------------------------------------------------------------------


class ItemsDomain:
    """Holds bootstrapped service instances for the *example* bounded context."""

    def __init__(self, service: ItemService) -> None:
        self.service = service

    async def aclose(self) -> None:
        """Called on shutdown — close pools / clients opened in bootstrap()."""


# ---------------------------------------------------------------------------
# Routes — thin delegates.  ResultRouter unwraps Success(...) into the response
# body and turns Failure(ItemError) into a problem response, using the
# ItemError.STATUS mapping; response_model is inferred from Result[T, ...].
# ---------------------------------------------------------------------------

_router = ResultRouter(prefix="/example", tags=["example"])


@_router.get("/")
async def list_items(svc: ItemServiceDep, ctx: RequestContextDep) -> Result[list[Item], ItemError]:
    return await svc.list_all(ctx)


@_router.post("/", status_code=status.HTTP_201_CREATED)
async def create_item(
    body: CreateItemRequest, svc: ItemServiceDep, ctx: RequestContextDep
) -> Result[Item, ItemError]:
    return await svc.create(body, ctx)


@_router.get("/{item_id}")
async def get_item(
    item_id: str, svc: ItemServiceDep, ctx: RequestContextDep
) -> Result[Item, ItemError]:
    return await svc.get(item_id, ctx)


@_router.patch("/{item_id}")
async def update_item(
    item_id: str, body: UpdateItemRequest, svc: ItemServiceDep, ctx: RequestContextDep
) -> Result[Item, ItemError]:
    return await svc.update(item_id, body, ctx)


@_router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: str, svc: ItemServiceDep, ctx: RequestContextDep
) -> Result[None, ItemError]:
    return await svc.delete(item_id, ctx)


def make_router() -> APIRouter:
    return _router


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


async def bootstrap(boot: BootstrapContext) -> ItemsDomain:
    """
    Wire storage → repository → service for the items domain.

    To swap the storage backend: replace ``InMemoryStore()`` with any class
    that satisfies the ``KeyValueStore`` protocol (e.g. a Redis-backed store),
    and close it in :meth:`ItemsDomain.aclose`.  Nothing else in this module —
    or in the service/repository layers — needs to change.
    """
    store: InMemoryStore[str, Item] = InMemoryStore()
    repository = ItemRepository(store=store)
    service = ItemService(
        repository=repository,
        audit_backend=boot.audit_backend,
        audit_integrity=boot.audit_integrity,
    )
    return ItemsDomain(service=service)
