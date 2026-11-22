from typing import TYPE_CHECKING

from returns.result import Failure, Result, Success

from consent_app.entities import Purpose
from consent_app.ports import PurposeExistsError, StorageUnavailableError

from .errors import ConsentError, ConsentErrorCode, consent_error

if TYPE_CHECKING:
    from consent_app.entities import NoticeVersion, PurposeSlug
    from consent_app.ports import Clock, ConsentUnitOfWorkFactory


class CreatePurpose:
    """Declare a processing purpose and the notice that explains it to subjects."""

    def __init__(self, uow: ConsentUnitOfWorkFactory, *, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def execute(
        self, slug: PurposeSlug, description: str, notice_version: NoticeVersion
    ) -> Result[Purpose, ConsentError]:
        now = self._clock.now()
        purpose = Purpose(
            slug=slug,
            description=description,
            notice_version=notice_version,
            notice_published_at=now,
            created_at=now,
        )
        try:
            async with self._uow() as uow:
                await uow.purposes.add(purpose)
        except PurposeExistsError:
            return Failure(consent_error(ConsentErrorCode.PURPOSE_EXISTS))
        except StorageUnavailableError:
            return Failure(consent_error(ConsentErrorCode.STORAGE_ERROR))
        return Success(purpose)
