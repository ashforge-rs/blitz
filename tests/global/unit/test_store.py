"""Unit tests for store.memory.InMemoryStore."""

from __future__ import annotations

import asyncio

import pytest

from store.memory import InMemoryStore


@pytest.fixture
def store() -> InMemoryStore[str, str]:
    return InMemoryStore()


async def test_get_missing_key_returns_none(store: InMemoryStore) -> None:
    assert await store.get("missing") is None


async def test_set_and_get_roundtrip(store: InMemoryStore) -> None:
    await store.set("k", "v")
    assert await store.get("k") == "v"


async def test_set_overwrites_existing_value(store: InMemoryStore) -> None:
    await store.set("k", "first")
    await store.set("k", "second")
    assert await store.get("k") == "second"


async def test_delete_existing_key_returns_true(store: InMemoryStore) -> None:
    await store.set("k", "v")
    assert await store.delete("k") is True
    assert await store.get("k") is None


async def test_delete_missing_key_returns_false(store: InMemoryStore) -> None:
    assert await store.delete("ghost") is False


async def test_exists_returns_true_when_present(store: InMemoryStore) -> None:
    await store.set("k", "v")
    assert await store.exists("k") is True


async def test_exists_returns_false_when_absent(store: InMemoryStore) -> None:
    assert await store.exists("nope") is False


async def test_keys_empty_on_new_store(store: InMemoryStore) -> None:
    assert await store.keys() == []


async def test_keys_returns_all_inserted_keys(store: InMemoryStore) -> None:
    await store.set("a", "1")
    await store.set("b", "2")
    assert sorted(await store.keys()) == ["a", "b"]


async def test_keys_does_not_include_deleted_key(store: InMemoryStore) -> None:
    await store.set("a", "1")
    await store.set("b", "2")
    await store.delete("a")
    assert await store.keys() == ["b"]


async def test_len_reflects_current_size(store: InMemoryStore) -> None:
    assert len(store) == 0
    await store.set("a", "1")
    assert len(store) == 1
    await store.delete("a")
    assert len(store) == 0


async def test_concurrent_writes_are_safe() -> None:
    """Multiple coroutines writing under the same key must not corrupt state."""
    store: InMemoryStore[str, int] = InMemoryStore()

    async def write(n: int) -> None:
        await store.set("counter", n)

    await asyncio.gather(*[write(i) for i in range(50)])
    # Whatever value ends up stored, it must be a valid integer 0-49
    val = await store.get("counter")
    assert val is not None
    assert 0 <= val <= 49


async def test_satisfies_key_value_store_protocol() -> None:
    from store.protocol import KeyValueStore

    store: InMemoryStore[str, str] = InMemoryStore()
    assert isinstance(store, KeyValueStore)
