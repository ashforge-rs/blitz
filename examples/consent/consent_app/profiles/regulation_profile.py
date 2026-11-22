from dataclasses import dataclass
from datetime import datetime, timedelta  # noqa: TC003 — dataclass field types
from enum import StrEnum

from consent_app.entities import (
    ConsentDecision,
    ConsentEvent,
    ConsentMethod,
    ConsentState,
    ConsentStatus,
    Purpose,
)


class ConsentModel(StrEnum):
    #: Processing needs a recorded grant.
    OPT_IN = "opt_in"
    #: Processing is allowed until the subject objects.
    OPT_OUT = "opt_out"


@dataclass(frozen=True, slots=True)
class RegulationProfile:
    """The consent rules of one regulation, as data.  The core knows no regulation by name.

    A deployment runs under one profile (``CONSENT_PROFILE``); every event records
    which one, so a decision can always be judged by the rules it was made under.
    """

    name: str
    model: ConsentModel
    #: Methods that count as a valid grant.  Withdrawal never has a method requirement.
    accepted_methods: frozenset[ConsentMethod]
    #: How long a grant stays valid; ``None`` means until withdrawn.
    max_validity: timedelta | None
    #: Whether a grant lapses when the purpose's notice changes.
    renew_on_notice_change: bool

    def accepts(self, method: ConsentMethod) -> bool:
        return method in self.accepted_methods

    def status(self, purpose: Purpose, latest: ConsentEvent | None, now: datetime) -> ConsentStatus:
        """Whether processing may go ahead, from the subject's latest decision."""
        if latest is None:
            # Never asked: an opt-in regime forbids processing, an opt-out regime allows it.
            return ConsentStatus(
                purpose.slug, ConsentState.NOT_GIVEN, may_process=self.model is ConsentModel.OPT_OUT
            )
        if latest.decision is ConsentDecision.WITHDRAWN:
            return self._status(latest, ConsentState.WITHDRAWN, may_process=False)
        if self.max_validity is not None and now - latest.recorded_at >= self.max_validity:
            return self._status(latest, ConsentState.EXPIRED, may_process=False)
        if self.renew_on_notice_change and latest.notice_version != purpose.notice_version:
            return self._status(latest, ConsentState.RENEWAL_REQUIRED, may_process=False)
        return self._status(latest, ConsentState.GRANTED, may_process=True)

    @staticmethod
    def _status(event: ConsentEvent, state: ConsentState, *, may_process: bool) -> ConsentStatus:
        return ConsentStatus(
            event.purpose,
            state,
            may_process=may_process,
            since=event.recorded_at,
            event_id=event.id,
        )
