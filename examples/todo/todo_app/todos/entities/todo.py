from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 — dataclass field type, resolved at runtime

from .title import Title  # noqa: TC001 — dataclass field type


@dataclass(frozen=True, slots=True)
class Todo:
    id: str
    #: A user id.  Todos reference users by id only; the contexts share no types.
    owner_id: str
    title: Title
    done: bool
    created_at: datetime
