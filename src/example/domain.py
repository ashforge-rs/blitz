from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, status

from store.memory import InMemoryStore

from .dependencies import ItemServiceDep, RequestContextDep
from .models import CreateItemRequest, Item, UpdateItemRequest
from .repository import ItemRepository
from .service import ItemService

if TYPE_CHECKING:
    from config import Settings


# ---------------------------------------------------------------------------
# Domain container
# ---------------------------------------------------------------------------


class ItemsDomain:
    """Holds bootstrapped service instances for the *example* bounded context."""

    def __init__(self, service: ItemService) -> None:
        self.service = service


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_router = APIRouter(prefix="/example", tags=["example"])


@_router.get("/", response_model=list[Item])
async def list_items(service: ItemServiceDep, ctx: RequestContextDep) -> list[Item]:
    return await service.list_all(ctx)


@_router.post("/", response_model=Item, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: CreateItemRequest, service: ItemServiceDep, ctx: RequestContextDep
) -> Item:
    return await service.create(body, ctx)


@_router.get("/{item_id}", response_model=Item)
async def get_item(item_id: str, service: ItemServiceDep, ctx: RequestContextDep) -> Item:
    item = await service.get(item_id, ctx)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


@_router.patch("/{item_id}", response_model=Item)
async def update_item(
    item_id: str, body: UpdateItemRequest, service: ItemServiceDep, ctx: RequestContextDep
) -> Item:
    item = await service.update(item_id, body, ctx)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


@_router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: str, service: ItemServiceDep, ctx: RequestContextDep) -> None:
    deleted = await service.delete(item_id, ctx)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")


def make_router() -> APIRouter:
    return _router


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


async def bootstrap(settings: Settings, **kwargs: Any) -> ItemsDomain:
    """
    Wires together the storage, repository, and service for the items domain.

    To swap the storage backend: replace ``InMemoryStore()`` with any class
    that satisfies the ``KeyValueStore`` protocol (e.g. a Redis-backed store).
    Nothing else in this module — or in the service/repository layers — needs
    to change (Dependency Inversion Principle).
    """
    store: InMemoryStore[str, Item] = InMemoryStore()
    repository = ItemRepository(store=store)
    service = ItemService(repository=repository)
    return ItemsDomain(service=service)
