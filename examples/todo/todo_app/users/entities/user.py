from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 — dataclass field type, resolved at runtime

from .display_name import DisplayName  # noqa: TC001 — dataclass field type
from .email_address import EmailAddress  # noqa: TC001 — dataclass field type


@dataclass(frozen=True, slots=True)
class User:
    id: str
    email: EmailAddress
    name: DisplayName
    created_at: datetime
