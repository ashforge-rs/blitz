"""Request and response bodies.  Validation is delegated to the value objects, so each
rule exists once (in ``entities/``) and a violation is still a 422 here."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from consent_app.entities import (
    ConsentDecision,
    ConsentEvent,
    ConsentMethod,
    ConsentState,
    ConsentStatus,
    NoticeVersion,
    Purpose,
    PurposeSlug,
    SubjectId,
)
from consent_app.use_cases import ConsentRecorded

SlugField = Annotated[str, AfterValidator(lambda v: PurposeSlug(v).value)]
NoticeField = Annotated[str, AfterValidator(lambda v: NoticeVersion(v).value)]
SubjectField = Annotated[str, AfterValidator(lambda v: SubjectId(v).value)]
SourceField = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^\S(.*\S)?$")]
EventIdField = Annotated[
    str | None,
    Field(
        default=None,
        min_length=8,
        max_length=64,
        pattern=r"^[\x21-\x7e]+$",
        description="Client-chosen unique id: a retry with the same id records nothing new.",
    ),
]


class PurposeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: SlugField
    description: str = Field(min_length=1, max_length=Purpose.MAX_DESCRIPTION)
    notice_version: NoticeField


class NoticeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notice_version: NoticeField


class GrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: SlugField
    #: The notice version the subject was shown when deciding.
    notice_version: NoticeField
    method: ConsentMethod
    source: SourceField
    event_id: EventIdField


class WithdrawalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: SlugField
    source: SourceField
    event_id: EventIdField


class PurposeResponse(BaseModel):
    slug: str
    description: str
    notice_version: str
    notice_published_at: datetime
    created_at: datetime

    @classmethod
    def of(cls, purpose: Purpose) -> PurposeResponse:
        return cls(
            slug=purpose.slug.value,
            description=purpose.description,
            notice_version=purpose.notice_version.value,
            notice_published_at=purpose.notice_published_at,
            created_at=purpose.created_at,
        )


class ConsentEventResponse(BaseModel):
    id: str
    subject_id: str
    purpose: str
    decision: ConsentDecision
    notice_version: str | None
    method: ConsentMethod | None
    source: str
    recorded_by: str
    profile: str
    recorded_at: datetime

    @classmethod
    def of(cls, event: ConsentEvent) -> ConsentEventResponse:
        return cls(
            id=event.id,
            subject_id=event.subject.value,
            purpose=event.purpose.value,
            decision=event.decision,
            notice_version=event.notice_version.value if event.notice_version else None,
            method=event.method,
            source=event.source,
            recorded_by=event.recorded_by,
            profile=event.profile,
            recorded_at=event.recorded_at,
        )


class ConsentStatusResponse(BaseModel):
    purpose: str
    state: ConsentState
    may_process: bool
    since: datetime | None
    event_id: str | None

    @classmethod
    def of(cls, status: ConsentStatus) -> ConsentStatusResponse:
        return cls(
            purpose=status.purpose.value,
            state=status.state,
            may_process=status.may_process,
            since=status.since,
            event_id=status.event_id,
        )


class ConsentRecordedResponse(BaseModel):
    event: ConsentEventResponse
    status: ConsentStatusResponse

    @classmethod
    def of(cls, recorded: ConsentRecorded) -> ConsentRecordedResponse:
        return cls(
            event=ConsentEventResponse.of(recorded.event),
            status=ConsentStatusResponse.of(recorded.status),
        )
