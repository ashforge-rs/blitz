from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class DisplayName:
    value: str

    MAX_LENGTH: ClassVar[int] = 100

    def __post_init__(self) -> None:
        trimmed = self.value.strip()
        if not 1 <= len(trimmed) <= self.MAX_LENGTH:
            msg = f"name must be 1-{self.MAX_LENGTH} characters"
            raise ValueError(msg)
        object.__setattr__(self, "value", trimmed)
