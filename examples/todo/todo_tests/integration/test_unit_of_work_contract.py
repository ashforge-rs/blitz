"""Port contract tests: every implementation of a unit of work behaves alike.

Each test runs per implementation: the in-memory fake, SQLite, and Postgres when
``TODO_TEST_POSTGRES_URL`` is set (CI).  A fake that drifts from the real
adapters, or a dialect that behaves differently, fails here.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import pytest
from sqlalchemy import Table, select

from todo_app.kernel import (
    Actor,
    AuditOutcome,
    AuditRecord,
    IdempotencyKeyTakenError,
    IdempotencyRecord,
)
from todo_app.persistence import Database
from todo_app.todos.adapters.sql_tables import audit_outbox as todos_outbox
from todo_app.todos.adapters.sql_todos_unit_of_work import SqlTodosUnitOfWorkFactory
from todo_app.todos.entities import Title, Todo
from todo_app.todos.ports import TodosUnitOfWorkFactory
from todo_app.users.adapters.sql_tables import audit_outbox as users_outbox
from todo_app.users.adapters.sql_users_unit_of_work import SqlUsersUnitOfWorkFactory
from todo_app.users.entities import DisplayName, EmailAddress, User
from todo_app.users.ports import EmailTakenError, UsersUnitOfWorkFactory
from todo_tests.fakes import EPOCH, InMemoryTodosUnitOfWorkFactory, InMemoryUsersUnitOfWorkFactory
from todo_tests.storage import BACKENDS, open_migrated, url_for

ACTOR = Actor(user_id=None, correlation_id="req-1")


@dataclass
class Harness[F]:
    uow: F
    #: Ids of the audit entries that were committed.
    audit_ids: Callable[[], Awaitable[list[str]]]


def _user(user_id: str = "u1", email: str = "ada@example.com") -> User:
    return User(id=user_id, email=EmailAddress(email), name=DisplayName("Ada"), created_at=EPOCH)


def _todo(todo_id: str = "t1") -> Todo:
    return Todo(id=todo_id, owner_id="u1", title=Title("Buy milk"), done=False, created_at=EPOCH)


def _entry(entry_id: str) -> AuditRecord:
    return AuditRecord(
        id=entry_id,
        operation="test.op",
        outcome=AuditOutcome.SUCCESS,
        actor=ACTOR,
        occurred_at=EPOCH,
        details={"reason": "x"},
    )


def _idem(key: str, resource_id: str) -> IdempotencyRecord:
    return IdempotencyRecord(
        scope="s", key=key, request_fingerprint="f", resource_id=resource_id, created_at=EPOCH
    )


def _outbox_ids(db: Database, table: Table) -> Callable[[], Awaitable[list[str]]]:
    async def _ids() -> list[str]:
        async with db.transaction(read_only=True) as conn:
            return list((await conn.execute(select(table.c.id).order_by(table.c.seq))).scalars())

    return _ids


@pytest.fixture(params=["in-memory", *BACKENDS])
async def users(
    request: pytest.FixtureRequest, database_url: str
) -> AsyncIterator[Harness[UsersUnitOfWorkFactory]]:
    if request.param == "in-memory":
        fake = InMemoryUsersUnitOfWorkFactory()

        async def _fake_ids() -> list[str]:
            return [e.id for e in fake.state.audit]

        yield Harness(fake, _fake_ids)
        return
    db = await open_migrated(await url_for(request.param, database_url))
    yield Harness(SqlUsersUnitOfWorkFactory(db), _outbox_ids(db, users_outbox))
    await db.close()


@pytest.fixture(params=["in-memory", *BACKENDS])
async def todos(
    request: pytest.FixtureRequest, database_url: str
) -> AsyncIterator[Harness[TodosUnitOfWorkFactory]]:
    if request.param == "in-memory":
        fake = InMemoryTodosUnitOfWorkFactory()

        async def _fake_ids() -> list[str]:
            return [e.id for e in fake.state.audit]

        yield Harness(fake, _fake_ids)
        return
    db = await open_migrated(await url_for(request.param, database_url))
    yield Harness(SqlTodosUnitOfWorkFactory(db), _outbox_ids(db, todos_outbox))
    await db.close()


# --- users -------------------------------------------------------------------


async def test_users_committed_changes_are_visible_afterwards(
    users: Harness[UsersUnitOfWorkFactory],
) -> None:
    async with users.uow() as uow:
        await uow.users.add(_user())
        await uow.api_tokens.add("hash-1", "u1", EPOCH)
        await uow.audit.record(_entry("a1"))

    async with users.uow(read_only=True) as uow:
        assert await uow.users.get("u1") == _user()
        assert await uow.users.find_by_token_hash("hash-1") == _user()
        assert await uow.users.find_by_token_hash("unknown") is None
    assert await users.audit_ids() == ["a1"]


async def test_users_an_error_discards_every_change(users: Harness[UsersUnitOfWorkFactory]) -> None:
    async def failing_unit() -> None:
        async with users.uow() as uow:
            await uow.users.add(_user())
            await uow.api_tokens.add("hash-1", "u1", EPOCH)
            await uow.audit.record(_entry("a1"))
            await uow.idempotency.add(_idem("k", "u1"))
            raise RuntimeError

    with pytest.raises(RuntimeError):
        await failing_unit()

    async with users.uow(read_only=True) as uow:
        assert await uow.users.get("u1") is None
        assert await uow.idempotency.get("s", "k") is None
    assert await users.audit_ids() == []


async def test_users_duplicate_email_raises_the_port_error(
    users: Harness[UsersUnitOfWorkFactory],
) -> None:
    async with users.uow() as uow:
        await uow.users.add(_user("u1"))

    async def second() -> None:
        async with users.uow() as uow:
            await uow.users.add(_user("u2"))

    with pytest.raises(EmailTakenError):
        await second()


async def test_users_revoking_a_token_leaves_the_others(
    users: Harness[UsersUnitOfWorkFactory],
) -> None:
    async with users.uow() as uow:
        await uow.users.add(_user())
        await uow.api_tokens.add("old", "u1", EPOCH)
        await uow.api_tokens.add("new", "u1", EPOCH)
    async with users.uow() as uow:
        await uow.api_tokens.revoke("old")

    async with users.uow(read_only=True) as uow:
        assert await uow.users.find_by_token_hash("old") is None
        assert await uow.users.find_by_token_hash("new") == _user()


async def test_users_idempotency_add_then_replace(users: Harness[UsersUnitOfWorkFactory]) -> None:
    async with users.uow() as uow:
        await uow.idempotency.add(_idem("k", "first"))
    async with users.uow() as uow:
        await uow.idempotency.replace(_idem("k", "second"))

    async with users.uow(read_only=True) as uow:
        record = await uow.idempotency.get("s", "k")
    assert record == _idem("k", "second")


async def test_users_adding_a_taken_key_raises_and_leaves_the_unit_usable(
    users: Harness[UsersUnitOfWorkFactory],
) -> None:
    async with users.uow() as uow:
        await uow.idempotency.add(_idem("k", "first"))

    async with users.uow() as uow:
        with pytest.raises(IdempotencyKeyTakenError):
            await uow.idempotency.add(_idem("k", "second"))
        await uow.users.add(_user())  # the transaction survived the violation

    async with users.uow(read_only=True) as uow:
        assert await uow.users.get("u1") == _user()
        assert (await uow.idempotency.get("s", "k")) == _idem("k", "first")


async def test_users_read_only_units_never_persist(users: Harness[UsersUnitOfWorkFactory]) -> None:
    async with users.uow(read_only=True) as uow:
        await uow.users.add(_user())

    async with users.uow(read_only=True) as uow:
        assert await uow.users.get("u1") is None


async def test_sql_repositories_refuse_use_outside_the_unit(db: Database) -> None:
    uow = SqlUsersUnitOfWorkFactory(db)()  # not entered

    with pytest.raises(RuntimeError, match="not open"):
        _ = uow.users


# --- todos -------------------------------------------------------------------


async def test_todos_committed_changes_are_visible_afterwards(
    todos: Harness[TodosUnitOfWorkFactory],
) -> None:
    async with todos.uow() as uow:
        await uow.todos.add(_todo())
        await uow.audit.record(_entry("a1"))

    async with todos.uow(read_only=True) as uow:
        assert await uow.todos.get("t1") == _todo()
        assert await uow.todos.get("missing") is None
    assert await todos.audit_ids() == ["a1"]


async def test_todos_an_error_discards_every_change(todos: Harness[TodosUnitOfWorkFactory]) -> None:
    async def failing_unit() -> None:
        async with todos.uow() as uow:
            await uow.todos.add(_todo())
            await uow.audit.record(_entry("a1"))
            await uow.idempotency.add(_idem("k", "t1"))
            raise RuntimeError

    with pytest.raises(RuntimeError):
        await failing_unit()

    async with todos.uow(read_only=True) as uow:
        assert await uow.todos.get("t1") is None
        assert await uow.idempotency.get("s", "k") is None
    assert await todos.audit_ids() == []


async def test_todos_adding_a_taken_key_raises(todos: Harness[TodosUnitOfWorkFactory]) -> None:
    async with todos.uow() as uow:
        await uow.idempotency.add(_idem("k", "t1"))

    async def again() -> None:
        async with todos.uow() as uow:
            await uow.idempotency.add(_idem("k", "t2"))

    with pytest.raises(IdempotencyKeyTakenError):
        await again()
