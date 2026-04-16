"""Unit tests for example.service.ItemService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from returns.pipeline import is_successful
from returns.result import Failure, Success

from audit.backends.noop import NoopAuditBackend
from audit.integrity import NoIntegrity
from domains.example.errors import ItemErrorCode
from domains.example.models import CreateItemRequest, Item, UpdateItemRequest
from domains.example.repository import ItemRepository
from domains.example.service import ItemService
from store.memory import InMemoryStore


@pytest.fixture
def repo() -> ItemRepository:
    store: InMemoryStore[str, Item] = InMemoryStore()
    return ItemRepository(store=store)


@pytest.fixture
def service(repo: ItemRepository) -> ItemService:
    return ItemService(
        repository=repo,
        audit_backend=NoopAuditBackend(),
        audit_integrity=NoIntegrity(),
    )


@pytest.fixture
def ctx() -> MagicMock:
    """Fake RequestContext with plausible HTTP request attributes."""
    mock = MagicMock()
    mock.request_id = "test-request-id"
    mock.get.return_value = None  # no principal by default
    mock._request.client.host = "127.0.0.1"
    mock._request.client.port = 54321
    mock._request.url.path = "/example/"
    return mock


async def test_list_all_empty(service: ItemService, ctx: MagicMock) -> None:
    result = await service.list_all(ctx)
    assert result == Success([])


async def test_create_returns_item_with_uuid(service: ItemService, ctx: MagicMock) -> None:
    req = CreateItemRequest(name="Widget")
    result = await service.create(req, ctx)
    assert is_successful(result)
    item = result.unwrap()
    assert item.name == "Widget"
    assert len(item.id) == 36  # UUID4 format


async def test_create_stores_data_payload(service: ItemService, ctx: MagicMock) -> None:
    req = CreateItemRequest(name="Widget", data={"color": "red"})
    result = await service.create(req, ctx)
    assert result.unwrap().data == {"color": "red"}


async def test_create_writes_id_onto_ctx(service: ItemService, ctx: MagicMock) -> None:
    req = CreateItemRequest(name="Widget")
    item = (await service.create(req, ctx)).unwrap()
    ctx.set.assert_called_with("last_created_item_id", item.id)


async def test_get_returns_created_item(service: ItemService, ctx: MagicMock) -> None:
    req = CreateItemRequest(name="Widget")
    created = (await service.create(req, ctx)).unwrap()
    found = await service.get(created.id, ctx)
    assert found == Success(created)


async def test_get_returns_not_found_for_missing(service: ItemService, ctx: MagicMock) -> None:
    result = await service.get("ghost", ctx)
    assert isinstance(result, Failure)
    assert result.failure().code == ItemErrorCode.NOT_FOUND


async def test_list_all_reflects_created_items(service: ItemService, ctx: MagicMock) -> None:
    for i in range(3):
        await service.create(CreateItemRequest(name=f"Item {i}"), ctx)
    result = await service.list_all(ctx)
    assert len(result.unwrap()) == 3


async def test_update_changes_name(service: ItemService, ctx: MagicMock) -> None:
    item = (await service.create(CreateItemRequest(name="Old"), ctx)).unwrap()
    result = await service.update(item.id, UpdateItemRequest(name="New"), ctx)
    assert result.unwrap().name == "New"


async def test_update_changes_data(service: ItemService, ctx: MagicMock) -> None:
    item = (await service.create(CreateItemRequest(name="Widget"), ctx)).unwrap()
    result = await service.update(item.id, UpdateItemRequest(data={"k": "v"}), ctx)
    assert result.unwrap().data == {"k": "v"}


async def test_update_preserves_unchanged_fields(service: ItemService, ctx: MagicMock) -> None:
    item = (await service.create(CreateItemRequest(name="Widget", data={"x": 1}), ctx)).unwrap()
    result = await service.update(item.id, UpdateItemRequest(name="NewName"), ctx)
    assert result.unwrap().data == {"x": 1}


async def test_update_bumps_updated_at(service: ItemService, ctx: MagicMock) -> None:
    item = (await service.create(CreateItemRequest(name="Widget"), ctx)).unwrap()
    updated = (await service.update(item.id, UpdateItemRequest(name="New"), ctx)).unwrap()
    assert updated.updated_at >= item.updated_at


async def test_update_writes_id_onto_ctx(service: ItemService, ctx: MagicMock) -> None:
    item = (await service.create(CreateItemRequest(name="Widget"), ctx)).unwrap()
    ctx.set.reset_mock()
    await service.update(item.id, UpdateItemRequest(name="New"), ctx)
    ctx.set.assert_called_with("last_updated_item_id", item.id)


async def test_update_returns_not_found_for_missing(service: ItemService, ctx: MagicMock) -> None:
    result = await service.update("ghost", UpdateItemRequest(name="X"), ctx)
    assert isinstance(result, Failure)
    assert result.failure().code == ItemErrorCode.NOT_FOUND


async def test_delete_returns_ok_for_existing(service: ItemService, ctx: MagicMock) -> None:
    item = (await service.create(CreateItemRequest(name="Widget"), ctx)).unwrap()
    result = await service.delete(item.id, ctx)
    assert result == Success(None)


async def test_delete_returns_not_found_for_missing(service: ItemService, ctx: MagicMock) -> None:
    result = await service.delete("ghost", ctx)
    assert isinstance(result, Failure)
    assert result.failure().code == ItemErrorCode.NOT_FOUND


async def test_delete_writes_id_onto_ctx(service: ItemService, ctx: MagicMock) -> None:
    item = (await service.create(CreateItemRequest(name="Widget"), ctx)).unwrap()
    ctx.set.reset_mock()
    await service.delete(item.id, ctx)
    ctx.set.assert_called_with("last_deleted_item_id", item.id)


async def test_delete_removes_item_from_list(service: ItemService, ctx: MagicMock) -> None:
    item = (await service.create(CreateItemRequest(name="Widget"), ctx)).unwrap()
    await service.delete(item.id, ctx)
    assert await service.list_all(ctx) == Success([])


# ---------------------------------------------------------------------------
# SOC 2 / Audit surface
# ---------------------------------------------------------------------------


async def test_create_sets_created_by_from_principal(repo: ItemRepository, ctx: MagicMock) -> None:
    """CC6: created_by records the authenticated principal."""
    ctx.get.return_value = "alice@example.com"
    svc = ItemService(
        repository=repo,
        audit_backend=NoopAuditBackend(),
        audit_integrity=NoIntegrity(),
    )
    item = (await svc.create(CreateItemRequest(name="Widget"), ctx)).unwrap()
    assert item.created_by == "alice@example.com"
    assert item.updated_by == "alice@example.com"


async def test_update_sets_updated_by_from_principal(repo: ItemRepository, ctx: MagicMock) -> None:
    """CC6: updated_by reflects the principal who made the change."""
    ctx.get.return_value = "bob@example.com"
    svc = ItemService(
        repository=repo,
        audit_backend=NoopAuditBackend(),
        audit_integrity=NoIntegrity(),
    )
    item = (await svc.create(CreateItemRequest(name="Widget"), ctx)).unwrap()
    updated = (await svc.update(item.id, UpdateItemRequest(name="New"), ctx)).unwrap()
    assert updated.updated_by == "bob@example.com"


async def test_create_emits_audit_event(repo: ItemRepository, ctx: MagicMock) -> None:
    """CC8: a structured audit event is emitted for every item creation."""
    captured: list = []

    class CapturingBackend(NoopAuditBackend):
        async def log(self, event) -> None:  # type: ignore[override]
            captured.append(event)

    svc = ItemService(
        repository=repo,
        audit_backend=CapturingBackend(),
        audit_integrity=NoIntegrity(),
    )
    await svc.create(CreateItemRequest(name="Widget"), ctx)

    assert len(captured) == 1
    evt = captured[0]
    assert evt.metadata["operation"] == "items.create"
    from audit.backend import AuditResult

    assert evt.result == AuditResult.SUCCESS


async def test_delete_emits_audit_event(repo: ItemRepository, ctx: MagicMock) -> None:
    """CC8: a structured audit event is emitted for every item deletion."""
    captured: list = []

    class CapturingBackend(NoopAuditBackend):
        async def log(self, event) -> None:  # type: ignore[override]
            captured.append(event)

    svc = ItemService(
        repository=repo,
        audit_backend=CapturingBackend(),
        audit_integrity=NoIntegrity(),
    )
    item = (await svc.create(CreateItemRequest(name="Widget"), ctx)).unwrap()
    captured.clear()  # only care about the delete event
    await svc.delete(item.id, ctx)

    assert len(captured) == 1
    evt = captured[0]
    assert evt.metadata["operation"] == "items.delete"
    from audit.backend import AuditResult

    assert evt.result == AuditResult.SUCCESS


