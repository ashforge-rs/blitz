import re
from dataclasses import dataclass
from typing import ClassVar

_SUBJECT = re.compile(r"[\x21-\x7e]+")


@dataclass(frozen=True, slots=True)
class SubjectId:
    """The data subject, as the controller's systems identify them: a pseudonymous id.

    Data minimisation: the consent store never needs to know who a person *is*,
    so identifiers that look like contact details (an email address) are refused.
    """

    value: str

    MAX_LENGTH: ClassVar[int] = 128

    def __post_init__(self) -> None:
        if not 1 <= len(self.value) <= self.MAX_LENGTH or not _SUBJECT.fullmatch(self.value):
            msg = f"subject id must be 1-{self.MAX_LENGTH} printable characters without spaces"
            raise ValueError(msg)
        if "@" in self.value:
            msg = "use a pseudonymous subject id, not an email address"
            raise ValueError(msg)
