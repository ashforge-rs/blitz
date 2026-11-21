import uuid
from abc import ABC, abstractmethod


class IdGenerator(ABC):
    """Port: new unique identifiers."""

    @abstractmethod
    def new_id(self) -> str: ...


class Uuid7Ids(IdGenerator):
    """Time-ordered UUIDv7 strings: primary-key inserts stay index-friendly."""

    def new_id(self) -> str:
        return str(uuid.uuid7())
