from __future__ import annotations

import asyncio
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class InMemoryStore(Generic[K, V]):  # noqa: UP046
    """
    Thread-safe, in-process key-value store backed by a plain ``dict``.

    Satisfies the ``KeyValueStore[K, V]`` protocol without inheriting from it
    (structural subtyping).  Replace with a persistent backend by implementing
    the same protocol — no changes required in callers.

    A single ``asyncio.Lock`` guards all mutations so the store is safe when
    used from concurrent coroutines within one event-loop.
    """

    def __init__(self) -> None:
        self._data: dict[K, V] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: K) -> V | None:
        return self._data.get(key)

    async def set(self, key: K, value: V) -> None:
        async with self._lock:
            self._data[key] = value

    async def delete(self, key: K) -> bool:
        async with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    async def exists(self, key: K) -> bool:
        return key in self._data

    async def keys(self) -> list[K]:
        return list(self._data.keys())

    def __len__(self) -> int:
        return len(self._data)
