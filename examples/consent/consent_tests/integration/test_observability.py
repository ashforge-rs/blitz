"""Metrics, the best-effort audit copy, and /health."""

from collections.abc import Callable
from typing import Any

from httpx import AsyncClient

from consent_tests.fakes import RecordingAuditBackend

from .conftest import GRANT


async def test_decisions_and_refusals_are_counted(
    client: AsyncClient, newsletter: dict[str, Any], metric: Callable[..., float]
) -> None:
    labels = {"decision": "granted", "purpose": "newsletter", "profile": "gdpr"}
    granted = metric("consentapp_decisions_total", **labels)
    refused = metric("consentapp_refusals_total", code="method_not_accepted")

    await client.post("/v1/subjects/subj-ada/consents", json=GRANT)
    await client.post("/v1/subjects/subj-ada/consents", json=GRANT | {"method": "implied"})

    assert metric("consentapp_decisions_total", **labels) == granted + 1
    assert metric("consentapp_refusals_total", code="method_not_accepted") == refused + 1


async def test_decisions_are_copied_to_blitz_audit(
    client: AsyncClient, newsletter: dict[str, Any], audit_log: RecordingAuditBackend
) -> None:
    r = await client.post("/v1/subjects/subj-ada/consents", json=GRANT)

    [event] = audit_log.operations("consent.")
    assert (event.method, event.principal) == ("consent.granted", "tests")
    assert event.metadata["resource_id"] == r.json()["event"]["id"]


async def test_an_audit_outage_neither_fails_nor_loses_a_decision(
    client: AsyncClient, newsletter: dict[str, Any], audit_log: RecordingAuditBackend
) -> None:
    audit_log.fail_with = OSError("audit sink down")

    r = await client.post("/v1/subjects/subj-ada/consents", json=GRANT)

    assert r.status_code == 201
    history = (await client.get("/v1/subjects/subj-ada/history")).json()
    assert [e["id"] for e in history] == [r.json()["event"]["id"]]  # the ledger has the proof


async def test_health_reports_the_store_and_profile(anonymous: AsyncClient) -> None:
    r = await anonymous.get("/health")

    assert r.status_code == 200
    body = r.json()
    check = body.get("checks", body)["consent_store"]
    assert (check["healthy"], check["profile"]) == (True, "gdpr")
