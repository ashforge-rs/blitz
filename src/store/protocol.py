from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

K = TypeVar("K")
V = TypeVar("V")


@runtime_checkable
class KeyValueStore(Protocol[K, V]):
    """
    Minimal key-value storage abstraction (Dependency Inversion Principle).

    Consumers depend on this protocol, not on a concrete implementation.
    Swap ``InMemoryStore`` for a Redis, DynamoDB, or any other backend by
    providing a class that satisfies this interface — no consumer code changes.
    """

    async def get(self, key: K) -> V | None:
        """Return the value stored under *key*, or ``None`` if absent."""
        ...

    async def set(self, key: K, value: V) -> None:
        """Insert or overwrite *key* with *value*."""
        ...

    async def delete(self, key: K) -> bool:
        """Remove *key*.  Returns ``True`` if the key existed, ``False`` otherwise."""
        ...

    async def exists(self, key: K) -> bool:
        """Return ``True`` if *key* is present in the store."""
        ...

    async def keys(self) -> list[K]:
        """Return all keys currently in the store."""
        ...
