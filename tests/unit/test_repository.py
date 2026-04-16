"""Unit tests for example.repository.ItemRepository."""

from __future__ import annotations

from typing import Any

import pytest

from example.models import Item
from example.repository import ItemRepository
from store.memory import InMemoryStore


@pytest.fixture
def repo() -> ItemRepository:
    store: InMemoryStore[str, Item] = InMemoryStore()
    return ItemRepository(store=store)


def _make_item(**kwargs: Any) -> Item:
    defaults = {"id": "abc", "name": "Widget"}
    return Item(**(defaults | kwargs))


async def test_find_by_id_returns_none_when_absent(repo: ItemRepository) -> None:
    assert await repo.find_by_id("missing") is None


async def test_save_and_find_by_id(repo: ItemRepository) -> None:
    item = _make_item()
    saved = await repo.save(item)
    assert saved == item
    assert await repo.find_by_id("abc") == item


async def test_save_overwrites_existing_item(repo: ItemRepository) -> None:
    item = _make_item(name="Original")
    await repo.save(item)
    updated = item.model_copy(update={"name": "Updated"})
    await repo.save(updated)
    found = await repo.find_by_id("abc")
    assert found is not None
    assert found.name == "Updated"


async def test_delete_returns_true_for_existing(repo: ItemRepository) -> None:
    await repo.save(_make_item())
    assert await repo.delete("abc") is True


async def test_delete_returns_false_for_missing(repo: ItemRepository) -> None:
    assert await repo.delete("ghost") is False


async def test_delete_removes_item(repo: ItemRepository) -> None:
    await repo.save(_make_item())
    await repo.delete("abc")
    assert await repo.find_by_id("abc") is None


async def test_find_all_empty(repo: ItemRepository) -> None:
    assert await repo.find_all() == []


async def test_find_all_returns_all_saved(repo: ItemRepository) -> None:
    items = [_make_item(id=str(i), name=f"Item {i}") for i in range(3)]
    for item in items:
        await repo.save(item)
    result = await repo.find_all()
    assert sorted(r.id for r in result) == ["0", "1", "2"]


async def test_exists_true_after_save(repo: ItemRepository) -> None:
    await repo.save(_make_item())
    assert await repo.exists("abc") is True


async def test_exists_false_for_missing(repo: ItemRepository) -> None:
    assert await repo.exists("nope") is False


async def test_exists_false_after_delete(repo: ItemRepository) -> None:
    await repo.save(_make_item())
    await repo.delete("abc")
    assert await repo.exists("abc") is False
