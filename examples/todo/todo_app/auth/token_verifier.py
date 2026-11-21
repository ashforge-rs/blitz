from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from todo_app.kernel import Actor


class TokenVerifier(ABC):
    """The port the auth provider needs; implemented by the users context."""

    @abstractmethod
    async def verify(self, token: str, actor: Actor) -> str | None:
        """The user id for a valid token, ``None`` for an unknown one.  Raise on an outage."""
        ...
