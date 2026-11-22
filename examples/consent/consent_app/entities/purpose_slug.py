import re
from dataclasses import dataclass

_SLUG = re.compile(r"[a-z][a-z0-9_]{1,63}")


@dataclass(frozen=True, slots=True)
class PurposeSlug:
    """A processing purpose's stable identifier, e.g. ``marketing_email``.

    Consent is granular: one decision per purpose, never one for "everything".
    """

    value: str

    def __post_init__(self) -> None:
        if not _SLUG.fullmatch(self.value):
            msg = "purpose must be 2-64 characters: a lower-case letter, then a-z, 0-9 or _"
            raise ValueError(msg)
