from dataclasses import replace
from typing import TYPE_CHECKING

from returns.result import Failure, Result, Success

from consent_app.ports import StorageUnavailableError

from .errors import ConsentError, ConsentErrorCode, consent_error

if TYPE_CHECKING:
    from consent_app.entities import NoticeVersion, Purpose, PurposeSlug
    from consent_app.ports import Clock, ConsentUnitOfWorkFactory


class PublishNotice:
    """Publish a new version of a purpose's notice.

    Under a profile that renews on notice changes (GDPR), every earlier grant for
    the purpose becomes ``renewal_required`` until the subject decides again.
    """

    def __init__(self, uow: ConsentUnitOfWorkFactory, *, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def execute(
        self, slug: PurposeSlug, notice_version: NoticeVersion
    ) -> Result[Purpose, ConsentError]:
        try:
            async with self._uow() as uow:
                purpose = await uow.purposes.get(slug)
                if purpose is None:
                    return Failure(consent_error(ConsentErrorCode.PURPOSE_NOT_FOUND))
                if purpose.notice_version == notice_version:
                    return Failure(consent_error(ConsentErrorCode.NOTICE_UNCHANGED))
                updated = replace(
                    purpose, notice_version=notice_version, notice_published_at=self._clock.now()
                )
                await uow.purposes.publish_notice(updated)
        except StorageUnavailableError:
            return Failure(consent_error(ConsentErrorCode.STORAGE_ERROR))
        return Success(updated)
