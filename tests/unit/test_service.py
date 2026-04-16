"""Unit tests for example.service.ItemService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from example.models import CreateItemRequest, Item, UpdateItemRequest
from example.repository import ItemRepository
from example.service import ItemService
from store.memory import InMemoryStore


@pytest.fixture
def repo() -> ItemRepository:
    store: InMemoryStore[str, Item] = InMemoryStore()
    return ItemRepository(store=store)


@pytest.fixture
def service(repo: ItemRepository) -> ItemService:
    return ItemService(repository=repo)


@pytest.fixture
def ctx() -> MagicMock:
    """Fake RequestContext — only needs set()."""
    mock = MagicMock()
    mock.set = MagicMock()
    return mock


async def test_list_all_empty(service: ItemService, ctx: MagicMock) -> None:
    assert await service.list_all(ctx) == []


async def test_create_returns_item_with_uuid(service: ItemService, ctx: MagicMock) -> None:
    req = CreateItemRequest(name="Widget")
    item = await service.create(req, ctx)
    assert item.name == "Widget"
    assert len(item.id) == 36  # UUID4 format


async def test_create_stores_data_payload(service: ItemService, ctx: MagicMock) -> None:
    req = CreateItemRequest(name="Widget", data={"color": "red"})
    item = await service.create(req, ctx)
    assert item.data == {"color": "red"}


async def test_create_writes_id_onto_ctx(service: ItemService, ctx: MagicMock) -> None:
    req = CreateItemRequest(name="Widget")
    item = await service.create(req, ctx)
    ctx.set.assert_called_with("last_created_item_id", item.id)


async def test_get_returns_created_item(service: ItemService, ctx: MagicMock) -> None:
    req = CreateItemRequest(name="Widget")
    created = await service.create(req, ctx)
    found = await service.get(created.id, ctx)
    assert found == created


async def test_get_returns_none_for_missing(service: ItemService, ctx: MagicMock) -> None:
    assert await service.get("ghost", ctx) is None


async def test_list_all_reflects_created_items(service: ItemService, ctx: MagicMock) -> None:
    for i in range(3):
        await service.create(CreateItemRequest(name=f"Item {i}"), ctx)
    result = await service.list_all(ctx)
    assert len(result) == 3


async def test_update_changes_name(service: ItemService, ctx: MagicMock) -> None:
    item = await service.create(CreateItemRequest(name="Old"), ctx)
    updated = await service.update(item.id, UpdateItemRequest(name="New"), ctx)
    assert updated is not None
    assert updated.name == "New"


async def test_update_changes_data(service: ItemService, ctx: MagicMock) -> None:
    item = await service.create(CreateItemRequest(name="Widget"), ctx)
    updated = await service.update(item.id, UpdateItemRequest(data={"k": "v"}), ctx)
    assert updated is not None
    assert updated.data == {"k": "v"}


async def test_update_preserves_unchanged_fields(service: ItemService, ctx: MagicMock) -> None:
    item = await service.create(CreateItemRequest(name="Widget", data={"x": 1}), ctx)
    updated = await service.update(item.id, UpdateItemRequest(name="NewName"), ctx)
    assert updated is not None
    assert updated.data == {"x": 1}


async def test_update_bumps_updated_at(service: ItemService, ctx: MagicMock) -> None:
    item = await service.create(CreateItemRequest(name="Widget"), ctx)
    updated = await service.update(item.id, UpdateItemRequest(name="New"), ctx)
    assert updated is not None
    assert updated.updated_at >= item.updated_at


async def test_update_writes_id_onto_ctx(service: ItemService, ctx: MagicMock) -> None:
    item = await service.create(CreateItemRequest(name="Widget"), ctx)
    ctx.set.reset_mock()
    await service.update(item.id, UpdateItemRequest(name="New"), ctx)
    ctx.set.assert_called_with("last_updated_item_id", item.id)


async def test_update_returns_none_for_missing(service: ItemService, ctx: MagicMock) -> None:
    assert await service.update("ghost", UpdateItemRequest(name="X"), ctx) is None


async def test_delete_returns_true_for_existing(service: ItemService, ctx: MagicMock) -> None:
    item = await service.create(CreateItemRequest(name="Widget"), ctx)
    assert await service.delete(item.id, ctx) is True


async def test_delete_returns_false_for_missing(service: ItemService, ctx: MagicMock) -> None:
    assert await service.delete("ghost", ctx) is False


async def test_delete_writes_id_onto_ctx(service: ItemService, ctx: MagicMock) -> None:
    item = await service.create(CreateItemRequest(name="Widget"), ctx)
    ctx.set.reset_mock()
    await service.delete(item.id, ctx)
    ctx.set.assert_called_with("last_deleted_item_id", item.id)


async def test_delete_removes_item_from_list(service: ItemService, ctx: MagicMock) -> None:
    item = await service.create(CreateItemRequest(name="Widget"), ctx)
    await service.delete(item.id, ctx)
    assert await service.list_all(ctx) == []
