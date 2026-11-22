from typing import Annotated

from deps import AuditBackendDep, AuditIntegrityDep, RequestContextDep
from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from returns.pipeline import is_successful
from returns.result import Result
from routing import ResultRouter
from state import get_domain

from consent_app.adapters.auth import CurrentClientDep
from consent_app.container import ConsentDomain
from consent_app.entities import NoticeVersion, PurposeSlug, SubjectId
from consent_app.use_cases import ConsentError, ConsentRecorded

from .observability import DECISIONS, REFUSALS, audit_best_effort
from .problems import ConsentProblem, to_problem
from .schemas import (
    ConsentEventResponse,
    ConsentRecordedResponse,
    ConsentStatusResponse,
    GrantBody,
    NoticeBody,
    PurposeBody,
    PurposeResponse,
    SlugField,
    SubjectField,
    WithdrawalBody,
)


def _domain(request: Request) -> ConsentDomain:
    return get_domain(request, ConsentDomain)


DomainDep = Annotated[ConsentDomain, Depends(_domain)]
SubjectPath = Annotated[SubjectField, Path(description="Pseudonymous subject id")]
PurposePath = Annotated[SlugField, Path(description="Purpose slug")]


def _refused(error: ConsentError) -> ConsentProblem:
    REFUSALS.labels(code=error.code.value).inc()
    return to_problem(error)


purposes = ResultRouter(prefix="/purposes", tags=["purposes"])
subjects = ResultRouter(prefix="/subjects/{subject_id}", tags=["consent"])


@purposes.post("/", status_code=status.HTTP_201_CREATED)
async def create_purpose(
    body: PurposeBody, domain: DomainDep, client: CurrentClientDep
) -> Result[PurposeResponse, ConsentProblem]:
    """Declare a processing purpose and the notice subjects are shown for it."""
    result = await domain.create_purpose.execute(
        PurposeSlug(body.slug), body.description, NoticeVersion(body.notice_version)
    )
    return result.map(PurposeResponse.of).alt(_refused)


@purposes.get("/")
async def list_purposes(
    domain: DomainDep, client: CurrentClientDep
) -> Result[list[PurposeResponse], ConsentProblem]:
    result = await domain.list_purposes.execute()
    return result.map(lambda found: [PurposeResponse.of(p) for p in found]).alt(_refused)


@purposes.post("/{slug}/notices")
async def publish_notice(
    slug: PurposePath, body: NoticeBody, domain: DomainDep, client: CurrentClientDep
) -> Result[PurposeResponse, ConsentProblem]:
    """Publish a new notice version.  Under GDPR, existing grants then need renewal."""
    result = await domain.publish_notice.execute(
        PurposeSlug(slug), NoticeVersion(body.notice_version)
    )
    return result.map(PurposeResponse.of).alt(_refused)


async def _recorded(
    result: Result[ConsentRecorded, ConsentError],
    response: Response,
    ctx: RequestContextDep,
    backend: AuditBackendDep,
    integrity: AuditIntegrityDep,
) -> Result[ConsentRecordedResponse, ConsentProblem]:
    if is_successful(result):
        recorded = result.unwrap()
        if recorded.replayed:
            response.headers["Idempotent-Replayed"] = "true"
        else:
            event = recorded.event
            DECISIONS.labels(
                decision=event.decision.value, purpose=event.purpose.value, profile=event.profile
            ).inc()
            await audit_best_effort(backend, integrity, ctx, f"consent.{event.decision}", event.id)
    return result.map(ConsentRecordedResponse.of).alt(_refused)


@subjects.post("/consents", status_code=status.HTTP_201_CREATED)
async def give_consent(
    subject_id: SubjectPath,
    body: GrantBody,
    domain: DomainDep,
    client: CurrentClientDep,
    response: Response,
    ctx: RequestContextDep,
    backend: AuditBackendDep,
    integrity: AuditIntegrityDep,
) -> Result[ConsentRecordedResponse, ConsentProblem]:
    """Record that the subject granted consent for a purpose."""
    result = await domain.give_consent.execute(
        SubjectId(subject_id),
        PurposeSlug(body.purpose),
        NoticeVersion(body.notice_version),
        body.method,
        source=body.source,
        recorded_by=client,
        event_id=body.event_id,
    )
    return await _recorded(result, response, ctx, backend, integrity)


@subjects.post("/withdrawals", status_code=status.HTTP_201_CREATED)
async def withdraw_consent(
    subject_id: SubjectPath,
    body: WithdrawalBody,
    domain: DomainDep,
    client: CurrentClientDep,
    response: Response,
    ctx: RequestContextDep,
    backend: AuditBackendDep,
    integrity: AuditIntegrityDep,
) -> Result[ConsentRecordedResponse, ConsentProblem]:
    """Record that the subject withdrew consent for a purpose.  Always accepted."""
    result = await domain.withdraw_consent.execute(
        SubjectId(subject_id),
        PurposeSlug(body.purpose),
        source=body.source,
        recorded_by=client,
        event_id=body.event_id,
    )
    return await _recorded(result, response, ctx, backend, integrity)


@subjects.get("/consents")
async def consent_status(
    subject_id: SubjectPath,
    domain: DomainDep,
    client: CurrentClientDep,
    purpose: Annotated[SlugField | None, Query(description="Only this purpose")] = None,
) -> Result[list[ConsentStatusResponse], ConsentProblem]:
    """May the subject's data be processed, per purpose?  Ask before processing."""
    result = await domain.consent_status.execute(
        SubjectId(subject_id), PurposeSlug(purpose) if purpose else None
    )
    return result.map(lambda found: [ConsentStatusResponse.of(s) for s in found]).alt(_refused)


@subjects.get("/history")
async def consent_history(
    subject_id: SubjectPath, domain: DomainDep, client: CurrentClientDep
) -> Result[list[ConsentEventResponse], ConsentProblem]:
    """Every decision the subject made, oldest first: the evidence of consent."""
    result = await domain.consent_history.execute(SubjectId(subject_id))
    return result.map(lambda found: [ConsentEventResponse.of(e) for e in found]).alt(_refused)


router = APIRouter()
router.include_router(purposes)
router.include_router(subjects)
