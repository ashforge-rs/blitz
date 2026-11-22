from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 — dataclass field type, resolved at runtime

from .consent_decision import ConsentDecision  # noqa: TC001 — dataclass field type
from .consent_method import ConsentMethod  # noqa: TC001 — dataclass field type
from .notice_version import NoticeVersion  # noqa: TC001 — dataclass field type
from .purpose_slug import PurposeSlug  # noqa: TC001 — dataclass field type
from .subject_id import SubjectId  # noqa: TC001 — dataclass field type


@dataclass(frozen=True, slots=True)
class ConsentEvent:
    """One decision by one subject about one purpose: an entry in the append-only ledger.

    Together the events are the proof of consent: who decided, about what, under
    which notice, how, through which channel, recorded by which system, and when.
    """

    id: str
    subject: SubjectId
    purpose: PurposeSlug
    decision: ConsentDecision
    #: The notice shown when granting; ``None`` for a withdrawal.
    notice_version: NoticeVersion | None
    #: How a grant was expressed; ``None`` for a withdrawal (it must always be possible).
    method: ConsentMethod | None
    #: The channel, e.g. ``web-signup`` or ``support-call``.
    source: str
    #: The client system that recorded it (accountability).
    recorded_by: str
    #: The regulation profile in force when it was recorded.
    profile: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        for name in ("source", "recorded_by"):
            value: str = getattr(self, name)
            if not 1 <= len(value) <= 64 or not value.isprintable() or value != value.strip():
                msg = f"{name} must be 1-64 printable characters"
                raise ValueError(msg)

    def same_decision_as(self, other: ConsentEvent) -> bool:
        """Equal in substance: a retry of the same request, whatever its id and time."""
        return (
            self.subject == other.subject
            and self.purpose == other.purpose
            and self.decision == other.decision
            and self.notice_version == other.notice_version
            and self.method == other.method
            and self.source == other.source
        )
