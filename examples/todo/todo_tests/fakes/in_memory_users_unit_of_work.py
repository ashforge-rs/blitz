from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Self

from todo_app.kernel import AuditTrail, IdempotencyStore
from todo_app.users.ports import (
    ApiTokenRepository,
    EmailTakenError,
    UserRepository,
    UsersUnitOfWork,
    UsersUnitOfWorkFactory,
)

if TYPE_CHECKING:
    from datetime import datetime
    from types import TracebackType

    from todo_app.kernel import AuditRecord, IdempotencyRecord
    from todo_app.users.entities import User


@dataclass
class UsersState:
    users: dict[str, User] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)  # token_hash → user id
    audit: list[AuditRecord] = field(default_factory=list)
    idempotency: dict[tuple[str, str], IdempotencyRecord] = field(default_factory=dict)

    def copy(self) -> UsersState:
        return replace(
            self,
            users=dict(self.users),
            tokens=dict(self.tokens),
            audit=list(self.audit),
            idempotency=dict(self.idempotency),
        )


class InMemoryUsersUnitOfWorkFactory(UsersUnitOfWorkFactory):
    """``UsersUnitOfWorkFactory`` with real transaction semantics, in memory.

    Each unit of work edits a copy of :attr:`state`; the copy replaces it only
    on a clean exit, so a raised error discards every change, like SQLite.
    """

    def __init__(self) -> None:
        self.state = UsersState()
        self.commits = 0
        #: Set to make the next units of work fail on entry (simulates an outage or a bug).
        self.fail_with: Exception | None = None

    def __call__(self, *, read_only: bool = False) -> InMemoryUsersUnitOfWork:
        return InMemoryUsersUnitOfWork(self, read_only=read_only)


class InMemoryUsersUnitOfWork(UsersUnitOfWork):
    def __init__(self, factory: InMemoryUsersUnitOfWorkFactory, *, read_only: bool) -> None:
        self._factory = factory
        self._read_only = read_only
        self._work = factory.state.copy()

    @property
    def users(self) -> InMemoryUserRepository:
        return InMemoryUserRepository(self._work)

    @property
    def api_tokens(self) -> InMemoryApiTokenRepository:
        return InMemoryApiTokenRepository(self._work)

    @property
    def audit(self) -> InMemoryUsersAuditTrail:
        return InMemoryUsersAuditTrail(self._work)

    @property
    def idempotency(self) -> InMemoryUsersIdempotencyStore:
        return InMemoryUsersIdempotencyStore(self._work)

    async def __aenter__(self) -> Self:
        if self._factory.fail_with is not None:
            raise self._factory.fail_with
        self._work = self._factory.state.copy()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is None and not self._read_only:
            self._factory.state = self._work
            self._factory.commits += 1


class InMemoryUserRepository(UserRepository):
    def __init__(self, state: UsersState) -> None:
        self._s = state

    async def add(self, user: User) -> None:
        if any(u.email == user.email for u in self._s.users.values()):
            raise EmailTakenError
        self._s.users[user.id] = user

    async def get(self, user_id: str) -> User | None:
        return self._s.users.get(user_id)

    async def find_by_token_hash(self, token_hash: str) -> User | None:
        user_id = self._s.tokens.get(token_hash)
        return None if user_id is None else self._s.users.get(user_id)


class InMemoryApiTokenRepository(ApiTokenRepository):
    def __init__(self, state: UsersState) -> None:
        self._s = state

    async def add(self, token_hash: str, user_id: str, created_at: datetime) -> None:
        self._s.tokens[token_hash] = user_id

    async def revoke(self, token_hash: str) -> None:
        self._s.tokens.pop(token_hash, None)


class InMemoryUsersAuditTrail(AuditTrail):
    def __init__(self, state: UsersState) -> None:
        self._s = state

    async def record(self, entry: AuditRecord) -> None:
        self._s.audit.append(entry)


class InMemoryUsersIdempotencyStore(IdempotencyStore):
    def __init__(self, state: UsersState) -> None:
        self._s = state

    async def get(self, scope: str, key: str) -> IdempotencyRecord | None:
        return self._s.idempotency.get((scope, key))

    async def put(self, record: IdempotencyRecord) -> None:
        self._s.idempotency[(record.scope, record.key)] = record
