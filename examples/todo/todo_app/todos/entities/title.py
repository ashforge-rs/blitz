from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class Title:
    value: str

    MAX_LENGTH: ClassVar[int] = 200

    def __post_init__(self) -> None:
        trimmed = self.value.strip()
        if not 1 <= len(trimmed) <= self.MAX_LENGTH:
            msg = f"title must be 1-{self.MAX_LENGTH} characters"
            raise ValueError(msg)
        object.__setattr__(self, "value", trimmed)
