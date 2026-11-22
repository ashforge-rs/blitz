import re
from dataclasses import dataclass

_VERSION = re.compile(r"[\x21-\x7e]{1,64}")


@dataclass(frozen=True, slots=True)
class NoticeVersion:
    """Which version of the information shown to the subject a decision was made under.

    Recording it is what makes consent *informed* and demonstrable.
    """

    value: str

    def __post_init__(self) -> None:
        if not _VERSION.fullmatch(self.value):
            msg = "notice version must be 1-64 printable characters without spaces"
            raise ValueError(msg)
