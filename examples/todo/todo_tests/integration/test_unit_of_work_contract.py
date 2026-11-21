"""Port contract tests: the in-memory fakes and the SQLite adapters must behave alike.

Each test runs twice, once per implementation, so a fake that drifts from the
real adapter (or the other way round) fails here instead of hiding in unit tests.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import pytest

from todo_app.kernel import Actor, AuditOutcome, AuditRecord, IdempotencyRecord
from todo_app.persistence import Database
from todo_app.todos.adapters.sqlite_todos_unit_of_work import (
    MIGRATIONS as TODO_MIGRATIONS,
)
from todo_app.todos.adapters.sqlite_todos_unit_of_work import (
    OUTBOX_TABLE as TODOS_OUTBOX,
)
from todo_app.todos.adapters.sqlite_todos_unit_of_work import SqliteTodosUnitOfWorkFactory
from todo_app.todos.entities import Title, Todo
from todo_app.todos.ports import TodosUnitOfWorkFactory
from todo_app.users.adapters.sqlite_users_unit_of_work import (
    OUTBOX_TABLE as USERS_OUTBOX,
)
from todo_app.users.adapters.sqlite_users_unit_of_work import SqliteUsersUnitOfWorkFactory
from todo_app.users.entities import DisplayName, EmailAddress, User
from todo_app.users.ports import EmailTakenError, UsersUnitOfWorkFactory
from todo_tests.fakes import EPOCH, InMemoryTodosUnitOfWorkFactory, InMemoryUsersUnitOfWorkFactory

ACTOR = Actor(user_id=None, correlation_id="req-1")


@dataclass
class Harness[F]:
    uow: F
    #: Ids of the audit entries that were committed.
    audit_ids: Callable[[], Awaitable[list[str]]]


def _user(user_id: str = "u1", email: str = "ada@example.com") -> User:
    return User(id=user_id, email=EmailAddress(email), name=DisplayName("Ada"), created_at=EPOCH)


def _entry(entry_id: str) -> AuditRecord:
    return AuditRecord(
        id=entry_id,
        operation="test.op",
        outcome=AuditOutcome.SUCCESS,
        actor=ACTOR,
        occurred_at=EPOCH,
    )


def _idem(key: str, resource_id: str) -> IdempotencyRecord:
    return IdempotencyRecord(
        scope="s", key=key, request_fingerprint="f", resource_id=resource_id, created_at=EPOCH
    )


def _outbox_ids(db: Database, table: str) -> Callable[[], Awaitable[list[str]]]:
    async def _ids() -> list[str]:
        sql = f"SELECT id FROM {table} ORDER BY seq"  # noqa: S608 — constant table name
        rows = await db.query(lambda c: c.execute(sql).fetchall())
        return [r["id"] for r in rows]

    return _ids


@pytest.fixture(params=["in-memory", "sqlite"])
async def users(
    request: pytest.FixtureRequest, db: Database
) -> AsyncIterator[Harness[UsersUnitOfWorkFactory]]:
    if request.param == "in-memory":
        fake = InMemoryUsersUnitOfWorkFactory()

        async def _fake_ids() -> list[str]:
            return [e.id for e in fake.state.audit]

        yield Harness(fake, _fake_ids)
    else:
        yield Harness(SqliteUsersUnitOfWorkFactory(db), _outbox_ids(db, USERS_OUTBOX))


@pytest.fixture(params=["in-memory", "sqlite"])
async def todos(
    request: pytest.FixtureRequest, db: Database
) -> AsyncIterator[Harness[TodosUnitOfWorkFactory]]:
    if request.param == "in-memory":
        fake = InMemoryTodosUnitOfWorkFactory()

        async def _fake_ids() -> list[str]:
            return [e.id for e in fake.state.audit]

        yield Harness(fake, _fake_ids)
    else:
        yield Harness(SqliteTodosUnitOfWorkFactory(db), _outbox_ids(db, TODOS_OUTBOX))


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
            await uow.idempotency.put(_idem("k", "u1"))
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

    with pytest.raises(EmailTakenError):
        async with users.uow() as uow:
            await uow.users.add(_user("u2"))


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


async def test_users_idempotency_put_replaces_the_record(
    users: Harness[UsersUnitOfWorkFactory],
) -> None:
    async with users.uow() as uow:
        await uow.idempotency.put(_idem("k", "first"))
    async with users.uow() as uow:
        await uow.idempotency.put(_idem("k", "second"))

    async with users.uow(read_only=True) as uow:
        record = await uow.idempotency.get("s", "k")
    assert record is not None
    assert record.resource_id == "second"


async def test_users_read_only_units_never_persist(users: Harness[UsersUnitOfWorkFactory]) -> None:
    async with users.uow(read_only=True) as uow:
        await uow.users.add(_user())

    async with users.uow(read_only=True) as uow:
        assert await uow.users.get("u1") is None


# --- todos -------------------------------------------------------------------


def _todo(todo_id: str = "t1") -> Todo:
    return Todo(id=todo_id, owner_id="u1", title=Title("Buy milk"), done=False, created_at=EPOCH)


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
            await uow.idempotency.put(_idem("k", "t1"))
            raise RuntimeError

    with pytest.raises(RuntimeError):
        await failing_unit()

    async with todos.uow(read_only=True) as uow:
        assert await uow.todos.get("t1") is None
        assert await uow.idempotency.get("s", "k") is None
    assert await todos.audit_ids() == []


async def test_todos_context_owns_its_schema(db_path: str) -> None:
    # No users table, no foreign key: the todos context stands alone.
    db = await Database.connect(db_path, migrations=TODO_MIGRATIONS)
    async with SqliteTodosUnitOfWorkFactory(db)() as uow:
        await uow.todos.add(_todo())
    await db.close()
