from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from todo_app.users.ports import (
    ApiTokenRepository,
    EmailTakenError,
    UserRepository,
    UsersUnitOfWork,
    UsersUnitOfWorkFactory,
)

from .in_memory_unit_of_work import (
    InMemoryState,
    InMemoryUnitOfWork,
    InMemoryUnitOfWorkFactory,
    refuse_if_read_only,
)

if TYPE_CHECKING:
    from datetime import datetime

    from todo_app.users.entities import User


@dataclass
class UsersState(InMemoryState):
    users: dict[str, User] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)  # token_hash → user id


class InMemoryUsersUnitOfWorkFactory(InMemoryUnitOfWorkFactory[UsersState], UsersUnitOfWorkFactory):
    """``UsersUnitOfWorkFactory`` with real transaction semantics, in memory."""

    def __init__(self) -> None:
        super().__init__(UsersState())

    def __call__(self, *, read_only: bool = False) -> InMemoryUsersUnitOfWork:
        return InMemoryUsersUnitOfWork(self, read_only=read_only)


class InMemoryUsersUnitOfWork(InMemoryUnitOfWork[UsersState], UsersUnitOfWork):
    @property
    def users(self) -> InMemoryUserRepository:
        return InMemoryUserRepository(self._work, read_only=self._read_only)

    @property
    def api_tokens(self) -> InMemoryApiTokenRepository:
        return InMemoryApiTokenRepository(self._work, read_only=self._read_only)


class InMemoryUserRepository(UserRepository):
    def __init__(self, state: UsersState, *, read_only: bool) -> None:
        self._s = state
        self._read_only = read_only

    async def add(self, user: User) -> None:
        refuse_if_read_only(self._read_only)
        if any(u.email == user.email for u in self._s.users.values()):
            raise EmailTakenError
        self._s.users[user.id] = user

    async def get(self, user_id: str) -> User | None:
        return self._s.users.get(user_id)

    async def find_by_token_hash(self, token_hash: str) -> User | None:
        user_id = self._s.tokens.get(token_hash)
        return None if user_id is None else self._s.users.get(user_id)


class InMemoryApiTokenRepository(ApiTokenRepository):
    def __init__(self, state: UsersState, *, read_only: bool) -> None:
        self._s = state
        self._read_only = read_only

    async def add(self, token_hash: str, user_id: str, created_at: datetime) -> None:
        refuse_if_read_only(self._read_only)
        self._s.tokens[token_hash] = user_id

    async def revoke(self, token_hash: str) -> None:
        refuse_if_read_only(self._read_only)
        self._s.tokens.pop(token_hash, None)
