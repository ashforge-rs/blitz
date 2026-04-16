from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from service import Service

from .models import CreateItemRequest, Item, UpdateItemRequest
from .repository import ItemRepository

if TYPE_CHECKING:
    from context import RequestContext


class ItemService(Service):
    """
    Business logic for the *items* bounded context (Single Responsibility).

    Depends on ``ItemRepository``, not on any storage primitive directly
    (Dependency Inversion Principle).  Extend this class to add domain rules
    without modifying routing or persistence code (Open/Closed Principle).

    Every mutating method receives a ``RequestContext`` so that the caller's
    request ID, authenticated principal, and any other per-request metadata are
    available for audit trails and derived business rules without the service
    having to reach back into the HTTP layer.
    """

    def __init__(self, repository: ItemRepository) -> None:
        self._repo = repository

    async def get(self, item_id: str, ctx: RequestContext) -> Item | None:
        return await self._repo.find_by_id(item_id)

    async def list_all(self, ctx: RequestContext) -> list[Item]:
        return await self._repo.find_all()

    async def create(self, request: CreateItemRequest, ctx: RequestContext) -> Item:
        item = Item(
            id=str(uuid.uuid4()),
            name=request.name,
            data=request.data,
        )
        # Attach the caller's identity to the item for provenance.
        ctx.set("last_created_item_id", item.id)
        return await self._repo.save(item)

    async def update(
        self, item_id: str, request: UpdateItemRequest, ctx: RequestContext
    ) -> Item | None:
        item = await self._repo.find_by_id(item_id)
        if item is None:
            return None
        updated = item.model_copy(
            update={
                k: v
                for k, v in {
                    "name": request.name,
                    "data": request.data,
                }.items()
                if v is not None
            }
            | {"updated_at": datetime.now(UTC)}
        )
        ctx.set("last_updated_item_id", item_id)
        return await self._repo.save(updated)

    async def delete(self, item_id: str, ctx: RequestContext) -> bool:
        deleted = await self._repo.delete(item_id)
        if deleted:
            ctx.set("last_deleted_item_id", item_id)
        return deleted
