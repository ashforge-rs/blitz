from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from todo_app.users.entities import User


class EmailTakenError(Exception):
    """Raised by :meth:`UserRepository.add` when the email is already registered."""


class UserRepository(ABC):
    @abstractmethod
    async def add(self, user: User) -> None:
        """Store a new user; raise :class:`EmailTakenError` if the email is registered."""
        ...

    @abstractmethod
    async def get(self, user_id: str) -> User | None: ...

    @abstractmethod
    async def find_by_token_hash(self, token_hash: str) -> User | None: ...
