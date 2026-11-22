from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 — dataclass field type, resolved at runtime
from typing import ClassVar

from .notice_version import NoticeVersion  # noqa: TC001 — dataclass field type
from .purpose_slug import PurposeSlug  # noqa: TC001 — dataclass field type


@dataclass(frozen=True, slots=True)
class Purpose:
    """Something the controller processes personal data for, and the notice explaining it."""

    slug: PurposeSlug
    description: str
    notice_version: NoticeVersion
    notice_published_at: datetime
    created_at: datetime

    MAX_DESCRIPTION: ClassVar[int] = 500

    def __post_init__(self) -> None:
        description = self.description.strip()
        if not 1 <= len(description) <= self.MAX_DESCRIPTION:
            msg = f"description must be 1-{self.MAX_DESCRIPTION} characters"
            raise ValueError(msg)
        object.__setattr__(self, "description", description)
