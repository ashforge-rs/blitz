from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from consent_app.entities import Purpose, PurposeSlug


class PurposeRepository(ABC):
    """Port: the purposes the controller asks consent for, and their notice history."""

    @abstractmethod
    async def add(self, purpose: Purpose) -> None:
        """Store a new purpose and its first notice; raise ``PurposeExistsError`` on a duplicate."""

    @abstractmethod
    async def get(self, slug: PurposeSlug) -> Purpose | None: ...

    @abstractmethod
    async def all(self) -> list[Purpose]:
        """Every purpose, ordered by slug."""

    @abstractmethod
    async def publish_notice(self, purpose: Purpose) -> None:
        """Make ``purpose.notice_version`` current and keep it in the notice history."""
