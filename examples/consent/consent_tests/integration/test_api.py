"""The HTTP API end to end: purposes, decisions, status, history, errors."""

from typing import Any

import pytest
from httpx import AsyncClient

from .conftest import GRANT


async def test_every_endpoint_needs_an_api_key(anonymous: AsyncClient) -> None:
    for method, path in [
        ("GET", "/v1/purposes/"),
        ("POST", "/v1/subjects/s1/consents"),
        ("GET", "/v1/subjects/s1/consents"),
        ("GET", "/v1/subjects/s1/history"),
    ]:
        r = await anonymous.request(method, path, json=GRANT)
        assert r.status_code == 401, (method, path)


async def test_an_unknown_api_key_is_401(anonymous: AsyncClient) -> None:
    r = await anonymous.get("/v1/purposes/", headers={"Authorization": "Bearer csk_forged"})

    assert r.status_code == 401


async def test_grant_then_status_then_withdraw_then_history(
    client: AsyncClient, newsletter: dict[str, Any]
) -> None:
    granted = await client.post("/v1/subjects/subj-ada/consents", json=GRANT)
    assert granted.status_code == 201
    assert granted.json()["status"] == granted.json()["status"] | {
        "state": "granted",
        "may_process": True,
    }
    assert granted.json()["event"]["recorded_by"] == "tests"  # the authenticated client

    [status] = (await client.get("/v1/subjects/subj-ada/consents")).json()
    assert (status["purpose"], status["state"], status["may_process"]) == (
        "newsletter",
        "granted",
        True,
    )

    withdrawn = await client.post(
        "/v1/subjects/subj-ada/withdrawals", json={"purpose": "newsletter", "source": "email-link"}
    )
    assert withdrawn.json()["status"]["may_process"] is False

    history = (await client.get("/v1/subjects/subj-ada/history")).json()
    assert [(e["decision"], e["source"], e["profile"]) for e in history] == [
        ("granted", "web", "gdpr"),
        ("withdrawn", "email-link", "gdpr"),
    ]


async def test_a_pre_ticked_box_is_not_consent(
    client: AsyncClient, newsletter: dict[str, Any]
) -> None:
    r = await client.post(
        "/v1/subjects/subj-ada/consents", json=GRANT | {"method": "pre_ticked_box"}
    )

    assert r.status_code == 422
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["code"] == "method_not_accepted"


async def test_a_new_notice_requires_renewal(
    client: AsyncClient, newsletter: dict[str, Any]
) -> None:
    await client.post("/v1/subjects/subj-ada/consents", json=GRANT)

    published = await client.post(
        "/v1/purposes/newsletter/notices", json={"notice_version": "2026-06"}
    )
    [status] = (await client.get("/v1/subjects/subj-ada/consents?purpose=newsletter")).json()
    outdated = await client.post("/v1/subjects/subj-bob/consents", json=GRANT)

    assert published.json()["notice_version"] == "2026-06"
    assert (status["state"], status["may_process"]) == ("renewal_required", False)
    assert (outdated.status_code, outdated.json()["code"]) == (409, "notice_outdated")


async def test_a_retry_with_the_same_event_id_is_replayed(
    client: AsyncClient, newsletter: dict[str, Any]
) -> None:
    body = GRANT | {"event_id": "crm-evt-000001"}

    first = await client.post("/v1/subjects/subj-ada/consents", json=body)
    retry = await client.post("/v1/subjects/subj-ada/consents", json=body)
    reused = await client.post(
        "/v1/subjects/subj-ada/withdrawals",
        json={"purpose": "newsletter", "source": "web", "event_id": "crm-evt-000001"},
    )

    assert retry.headers["idempotent-replayed"] == "true"
    assert retry.json()["event"] == first.json()["event"]
    assert (reused.status_code, reused.json()["code"]) == (409, "event_id_reused")
    assert len((await client.get("/v1/subjects/subj-ada/history")).json()) == 1


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/v1/subjects/ada@example.com/consents", GRANT),
        ("/v1/subjects/subj-ada/consents", GRANT | {"method": "telepathy"}),
        ("/v1/subjects/subj-ada/consents", GRANT | {"purpose": "Newsletter"}),
        ("/v1/subjects/subj-ada/consents", GRANT | {"extra": 1}),
        ("/v1/subjects/subj-ada/consents", GRANT | {"source": " padded "}),
    ],
    ids=["email-as-subject", "unknown-method", "bad-slug", "unknown-field", "padded-source"],
)
async def test_invalid_input_is_422(
    client: AsyncClient, newsletter: dict[str, Any], path: str, body: dict[str, Any]
) -> None:
    r = await client.post(path, json=body)

    assert r.status_code == 422


async def test_an_unknown_purpose_is_404(client: AsyncClient) -> None:
    r = await client.post("/v1/subjects/subj-ada/consents", json=GRANT)

    assert (r.status_code, r.json()["code"]) == (404, "purpose_not_found")


async def test_a_duplicate_purpose_is_409(client: AsyncClient, newsletter: dict[str, Any]) -> None:
    r = await client.post(
        "/v1/purposes/", json={"slug": "newsletter", "description": "x", "notice_version": "v1"}
    )

    assert (r.status_code, r.json()["code"]) == (409, "purpose_exists")


async def test_purposes_are_listed(client: AsyncClient, newsletter: dict[str, Any]) -> None:
    r = await client.get("/v1/purposes/")

    assert [p["slug"] for p in r.json()] == ["newsletter"]
