from abc import ABC, abstractmethod


class IdGenerator(ABC):
    """Port: new unique identifiers for consent events."""

    @abstractmethod
    def new_id(self) -> str: ...
