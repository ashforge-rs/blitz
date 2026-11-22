from abc import ABC, abstractmethod
from datetime import datetime  # noqa: TC003 — part of the port's signature


class ApiTokenRepository(ABC):
    """API tokens by hash.  A user may hold several; revoking one leaves the others."""

    @abstractmethod
    async def add(self, token_hash: str, user_id: str, created_at: datetime) -> None: ...

    @abstractmethod
    async def revoke(self, token_hash: str) -> None: ...
