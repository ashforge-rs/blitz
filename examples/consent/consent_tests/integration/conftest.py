"""A purpose most API tests start from, and the grant body they send."""

from typing import Any

import pytest
from httpx import AsyncClient

GRANT = {
    "purpose": "newsletter",
    "notice_version": "2026-01",
    "method": "checkbox",
    "source": "web",
}


@pytest.fixture
async def newsletter(client: AsyncClient) -> dict[str, Any]:
    r = await client.post(
        "/v1/purposes/",
        json={
            "slug": "newsletter",
            "description": "Monthly newsletter",
            "notice_version": "2026-01",
        },
    )
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body
