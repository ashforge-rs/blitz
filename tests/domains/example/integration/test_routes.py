"""Integration tests for the /example HTTP routes."""

from __future__ import annotations

from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create(client: AsyncClient, name: str = "Widget", data: dict | None = None) -> dict:
    payload: dict = {"name": name}
    if data is not None:
        payload["data"] = data
    r = await client.post("/example/", json=payload)
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# LIST  GET /example/
# ---------------------------------------------------------------------------


async def test_list_empty_on_fresh_app(client: AsyncClient) -> None:
    r = await client.get("/example/")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_returns_created_items(client: AsyncClient) -> None:
    await _create(client, "Alpha")
    await _create(client, "Beta")
    r = await client.get("/example/")
    names = {i["name"] for i in r.json()}
    assert names == {"Alpha", "Beta"}


# ---------------------------------------------------------------------------
# CREATE  POST /example/
# ---------------------------------------------------------------------------


async def test_create_returns_201_with_body(client: AsyncClient) -> None:
    r = await client.post("/example/", json={"name": "Widget"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Widget"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_create_with_data_payload(client: AsyncClient) -> None:
    r = await client.post("/example/", json={"name": "Gadget", "data": {"sku": "G-001"}})
    assert r.status_code == 201
    assert r.json()["data"] == {"sku": "G-001"}


async def test_create_empty_name_returns_422(client: AsyncClient) -> None:
    r = await client.post("/example/", json={"name": ""})
    assert r.status_code == 422


async def test_create_missing_name_returns_422(client: AsyncClient) -> None:
    r = await client.post("/example/", json={})
    assert r.status_code == 422


async def test_create_name_too_long_returns_422(client: AsyncClient) -> None:
    r = await client.post("/example/", json={"name": "x" * 256})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET  GET /example/{id}
# ---------------------------------------------------------------------------


async def test_get_existing_item(client: AsyncClient) -> None:
    created = await _create(client, "Widget")
    r = await client.get(f"/example/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


async def test_get_missing_item_returns_404(client: AsyncClient) -> None:
    r = await client.get("/example/does-not-exist")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


# ---------------------------------------------------------------------------
# UPDATE  PATCH /example/{id}
# ---------------------------------------------------------------------------


async def test_update_name(client: AsyncClient) -> None:
    created = await _create(client, "Old")
    r = await client.patch(f"/example/{created['id']}", json={"name": "New"})
    assert r.status_code == 200
    assert r.json()["name"] == "New"
    assert r.json()["id"] == created["id"]


async def test_update_data(client: AsyncClient) -> None:
    created = await _create(client, "Widget")
    r = await client.patch(f"/example/{created['id']}", json={"data": {"k": "v"}})
    assert r.status_code == 200
    assert r.json()["data"] == {"k": "v"}


async def test_update_partial_preserves_other_fields(client: AsyncClient) -> None:
    created = await _create(client, "Widget", data={"x": 1})
    r = await client.patch(f"/example/{created['id']}", json={"name": "New"})
    assert r.status_code == 200
    assert r.json()["data"] == {"x": 1}


async def test_update_missing_item_returns_404(client: AsyncClient) -> None:
    r = await client.patch("/example/ghost", json={"name": "X"})
    assert r.status_code == 404


async def test_update_empty_body_is_noop(client: AsyncClient) -> None:
    created = await _create(client, "Widget")
    r = await client.patch(f"/example/{created['id']}", json={})
    assert r.status_code == 200
    assert r.json()["name"] == "Widget"


# ---------------------------------------------------------------------------
# DELETE  DELETE /example/{id}
# ---------------------------------------------------------------------------


async def test_delete_existing_item_returns_204(client: AsyncClient) -> None:
    created = await _create(client, "Widget")
    r = await client.delete(f"/example/{created['id']}")
    assert r.status_code == 204


async def test_delete_removes_item_from_list(client: AsyncClient) -> None:
    created = await _create(client, "Widget")
    await client.delete(f"/example/{created['id']}")
    r = await client.get("/example/")
    assert all(i["id"] != created["id"] for i in r.json())


async def test_delete_missing_item_returns_404(client: AsyncClient) -> None:
    r = await client.delete("/example/ghost")
    assert r.status_code == 404


async def test_delete_twice_returns_404_second_time(client: AsyncClient) -> None:
    created = await _create(client, "Widget")
    await client.delete(f"/example/{created['id']}")
    r = await client.delete(f"/example/{created['id']}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Request context propagation
# ---------------------------------------------------------------------------


async def test_request_id_echoed_in_response_header(client: AsyncClient) -> None:
    r = await client.get("/example/", headers={"X-Request-ID": "test-123"})
    assert r.headers.get("x-request-id") == "test-123"


async def test_request_id_generated_when_absent(client: AsyncClient) -> None:
    r = await client.get("/example/")
    assert len(r.headers["x-request-id"]) == 32  # UUID4 hex
