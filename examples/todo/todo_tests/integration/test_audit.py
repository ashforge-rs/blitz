"""Audit entries are committed with the change they describe, then delivered by the relay."""

import pytest
from httpx import AsyncClient

from audit.backend import AuditResult
from todo_app.kernel import StorageUnavailableError
from todo_app.users.adapters.sqlite_user_repository import SqliteUserRepository
from todo_tests.fakes import RecordingAuditBackend
from todo_tests.fixture_types import FlushAudit, Metric, RegisterUser


async def test_registration_is_audited_without_personal_data(
    register_user: RegisterUser, audit_log: RecordingAuditBackend, flush_audit: FlushAudit
) -> None:
    ada = await register_user(email="ada@example.com")
    await flush_audit()

    [event] = audit_log.operations("users.register")
    assert event.result is AuditResult.SUCCESS
    assert event.metadata["resource_id"] == ada["user"]["id"]
    assert "ada@example.com" not in repr(event)
    assert ada["api_token"] not in repr(event)


async def test_todo_creation_records_the_principal_and_request(
    client: AsyncClient,
    register_user: RegisterUser,
    audit_log: RecordingAuditBackend,
    flush_audit: FlushAudit,
) -> None:
    ada = await register_user()

    r = await client.post(
        "/v1/todos/",
        json={"title": "Buy milk"},
        headers={"Authorization": f"Bearer {ada['api_token']}"},
    )
    await flush_audit()

    [event] = audit_log.operations("todos.create")
    assert event.principal == ada["user"]["id"]
    assert event.metadata["resource_id"] == r.json()["id"]
    assert event.correlation_id == r.headers["x-request-id"]
    assert event.path == "/v1/todos/"


async def test_rejected_registration_is_audited_as_a_failure(
    client: AsyncClient,
    register_user: RegisterUser,
    audit_log: RecordingAuditBackend,
    flush_audit: FlushAudit,
) -> None:
    await register_user()
    await client.post("/v1/users/", json={"email": "ada@example.com", "name": "Ada"})
    await flush_audit()

    rejected = audit_log.operations("users.register")[-1]
    assert rejected.result is AuditResult.FAILURE
    assert rejected.metadata["reason"] == "email_taken"


async def test_audit_outage_neither_fails_nor_loses_a_registration(
    client: AsyncClient,
    register_user: RegisterUser,
    audit_log: RecordingAuditBackend,
    flush_audit: FlushAudit,
) -> None:
    """Regression: an audit failure used to 500 *after* the commit and lose the token."""
    audit_log.fail_with = OSError("audit sink unavailable")

    ada = await register_user()  # asserts 201
    await flush_audit()  # the relay can't deliver yet

    r = await client.post(
        "/v1/todos/",
        json={"title": "Milk"},
        headers={"Authorization": f"Bearer {ada['api_token']}"},
    )
    assert r.status_code == 201  # the token the client received works
    assert audit_log.operations("users.register") == []

    audit_log.fail_with = None
    await flush_audit()
    assert [e.metadata["resource_id"] for e in audit_log.operations("users.register")] == [
        ada["user"]["id"]
    ]


async def test_storage_outage_is_a_500_storage_error_and_counted(
    client: AsyncClient, metric: Metric, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(self: SqliteUserRepository, user: object) -> None:
        raise StorageUnavailableError("disk I/O error")

    monkeypatch.setattr(SqliteUserRepository, "add", unavailable)
    before = metric("todoapp_users_registered_total", result="error")

    r = await client.post("/v1/users/", json={"email": "ada@example.com", "name": "Ada"})

    assert r.status_code == 500
    assert r.json()["code"] == "storage_error"
    assert "disk" not in r.text
    assert metric("todoapp_users_registered_total", result="error") == before + 1


async def test_a_bug_surfaces_as_a_plain_500_not_a_storage_error(
    client: AsyncClient, metric: Metric, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def buggy(self: SqliteUserRepository, user: object) -> None:
        raise TypeError("adapter bug")

    monkeypatch.setattr(SqliteUserRepository, "add", buggy)
    before = metric("todoapp_users_registered_total", result="error")

    r = await client.post("/v1/users/", json={"email": "ada@example.com", "name": "Ada"})

    assert r.status_code == 500
    # blitz's unhandled-error path (sanitised in production), not a domain failure.
    assert "code" not in r.json()
    assert metric("todoapp_users_registered_total", result="error") == before
