"""
Fuzz / property-based tests using Hypothesis.

These tests generate arbitrary inputs and verify invariants that must always
hold regardless of the data — effectively finding edge cases no hand-written
test would think to cover.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from returns.pipeline import is_successful
from returns.result import Failure

from audit.backends.noop import NoopAuditBackend
from audit.integrity import NoIntegrity
from context import RequestContext
from domains.example.errors import ItemErrorCode
from domains.example.models import CreateItemRequest, Item, UpdateItemRequest
from domains.example.repository import ItemRepository
from domains.example.service import ItemService
from store.memory import InMemoryStore

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

valid_name = st.text(min_size=1, max_size=255)
optional_name = st.one_of(st.none(), valid_name)
json_value = st.recursive(
    st.one_of(st.none(), st.booleans(), st.integers(), st.floats(allow_nan=False), st.text()),
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=20), children, max_size=5),
    ),
    max_leaves=10,
)
data_dict = st.dictionaries(st.text(max_size=20), json_value, max_size=8)


def _make_service() -> tuple[ItemService, RequestContext]:
    """Return a fresh (service, fake_ctx) pair."""

    store: InMemoryStore[str, Item] = InMemoryStore()
    repo = ItemRepository(store=store)
    svc = ItemService(
        repository=repo,
        audit_backend=NoopAuditBackend(),
        audit_integrity=NoIntegrity(),
    )
    ctx = cast("RequestContext", MagicMock())
    ctx.request_id = "fuzz-ctx"
    ctx.get.return_value = None
    ctx._request.client = None  # exercises the None-safe remote_addr branch
    ctx._request.url.path = "/example/"
    return svc, ctx


def _run(coro: Any) -> Any:
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Model validation fuzz
# ---------------------------------------------------------------------------


@given(name=valid_name, data=data_dict)
def test_create_request_accepts_valid_inputs(name: str, data: dict) -> None:
    """Pydantic must accept any non-empty name up to 255 chars."""
    req = CreateItemRequest(name=name, data=data)
    assert req.name == name
    assert req.data == data


@given(name=st.text(min_size=256))
def test_create_request_rejects_name_too_long(name: str) -> None:
    """Names over 255 characters must be rejected by Pydantic."""
    with pytest.raises(Exception):  # noqa: B017  # ValidationError subclasses Exception; exact type is internal to Pydantic v2
        CreateItemRequest(name=name)


@given(name=optional_name, data=st.one_of(st.none(), data_dict))
def test_update_request_accepts_any_optional_combination(
    name: str | None, data: dict | None
) -> None:
    req = UpdateItemRequest(name=name, data=data)
    assert req.name == name
    assert req.data == data


# ---------------------------------------------------------------------------
# Service invariants
# ---------------------------------------------------------------------------


@given(name=valid_name, data=data_dict)
@settings(max_examples=50)
def test_create_then_get_roundtrip(name: str, data: dict) -> None:
    """get(id) must always return the item that was just created."""
    svc, ctx = _make_service()
    req = CreateItemRequest(name=name, data=data)
    item = _run(svc.create(req, ctx)).unwrap()
    found = _run(svc.get(item.id, ctx)).unwrap()
    assert found.name == name
    assert found.data == data


@given(name=valid_name, new_name=valid_name)
@settings(max_examples=50)
def test_update_name_is_reflected_in_get(name: str, new_name: str) -> None:
    svc, ctx = _make_service()
    item = _run(svc.create(CreateItemRequest(name=name), ctx)).unwrap()
    _run(svc.update(item.id, UpdateItemRequest(name=new_name), ctx)).unwrap()
    found = _run(svc.get(item.id, ctx)).unwrap()
    assert found.name == new_name


@given(name=valid_name)
@settings(max_examples=50)
def test_delete_removes_item(name: str) -> None:
    svc, ctx = _make_service()
    item = _run(svc.create(CreateItemRequest(name=name), ctx)).unwrap()
    assert is_successful(_run(svc.delete(item.id, ctx)))
    get_result = _run(svc.get(item.id, ctx))
    assert not is_successful(get_result)
    assert isinstance(get_result, Failure) and get_result.failure().code == ItemErrorCode.NOT_FOUND


@given(names=st.lists(valid_name, min_size=1, max_size=20, unique=True))
@settings(max_examples=30)
def test_list_all_count_matches_creates(names: list[str]) -> None:
    """list_all() must return exactly as many items as were created."""
    svc, ctx = _make_service()
    for n in names:
        _run(svc.create(CreateItemRequest(name=n), ctx))
    items = _run(svc.list_all(ctx)).unwrap()
    assert len(items) == len(names)


@given(name=valid_name, extra_id=st.uuids())
@settings(max_examples=30)
def test_delete_nonexistent_returns_not_found(name: str, extra_id: object) -> None:
    """Deleting an ID that was never created must return Failure(NOT_FOUND)."""
    svc, ctx = _make_service()
    item = _run(svc.create(CreateItemRequest(name=name), ctx)).unwrap()
    other_id = str(extra_id)
    if other_id == item.id:
        return  # skip degenerate collision case
    result = _run(svc.delete(other_id, ctx))
    assert isinstance(result, Failure) and result.failure().code == ItemErrorCode.NOT_FOUND


# ---------------------------------------------------------------------------
# Store-level fuzz
# ---------------------------------------------------------------------------


@given(key=st.text(max_size=50), value=st.text(max_size=200))
@settings(max_examples=100)
def test_store_set_get_roundtrip(key: str, value: str) -> None:
    store: InMemoryStore[str, str] = InMemoryStore()
    _run(store.set(key, value))
    assert _run(store.get(key)) == value


@given(key=st.text(max_size=50), value=st.text(max_size=200))
@settings(max_examples=50)
def test_store_delete_then_get_is_none(key: str, value: str) -> None:
    store: InMemoryStore[str, str] = InMemoryStore()
    _run(store.set(key, value))
    _run(store.delete(key))
    assert _run(store.get(key)) is None


@given(entries=st.dictionaries(st.text(max_size=20), st.text(max_size=50), max_size=20))
@settings(max_examples=50)
def test_store_keys_matches_inserted(entries: dict) -> None:
    store: InMemoryStore[str, str] = InMemoryStore()
    for k, v in entries.items():
        _run(store.set(k, v))
    assert sorted(_run(store.keys())) == sorted(entries.keys())
