import re
from dataclasses import dataclass
from typing import ClassVar

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(frozen=True, slots=True)
class EmailAddress:
    """A syntactically valid email, normalised (trimmed, lower-cased) on construction.

    Normalising here makes "Ada@Example.com" and "ada@example.com" the same
    account everywhere, not just at the HTTP edge.
    """

    value: str

    MAX_LENGTH: ClassVar[int] = 254

    def __post_init__(self) -> None:
        normalised = self.value.strip().lower()
        if len(normalised) > self.MAX_LENGTH or not _EMAIL.fullmatch(normalised):
            msg = "not a valid email address"  # never echo the value: it is personal data
            raise ValueError(msg)
        object.__setattr__(self, "value", normalised)
