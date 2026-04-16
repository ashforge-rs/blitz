from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from store.protocol import KeyValueStore

    from .models import Item


class ItemRepository:
    """
    Data-access layer for items (Single Responsibility Principle).

    Depends on the ``KeyValueStore`` *protocol*, not any concrete class
    (Dependency Inversion Principle).  Swap the underlying store — e.g. swap
    ``InMemoryStore`` for ``RedisStore`` — without touching this class or the
    service layer above it (Open/Closed Principle).
    """

    def __init__(self, store: KeyValueStore[str, Item]) -> None:
        self._store = store

    async def find_by_id(self, item_id: str) -> Item | None:
        return await self._store.get(item_id)

    async def save(self, item: Item) -> Item:
        await self._store.set(item.id, item)
        return item

    async def delete(self, item_id: str) -> bool:
        return await self._store.delete(item_id)

    async def find_all(self) -> list[Item]:
        keys = await self._store.keys()
        items = [await self._store.get(k) for k in keys]
        return [i for i in items if i is not None]

    async def exists(self, item_id: str) -> bool:
        return await self._store.exists(item_id)
