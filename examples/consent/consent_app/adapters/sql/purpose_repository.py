from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from consent_app.entities import NoticeVersion, Purpose, PurposeSlug
from consent_app.ports import PurposeExistsError, PurposeRepository

from .tables import purpose_notices, purposes

if TYPE_CHECKING:
    from sqlalchemy import RowMapping
    from sqlalchemy.ext.asyncio import AsyncConnection


class SqlPurposeRepository(PurposeRepository):
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, purpose: Purpose) -> None:
        try:
            await self._conn.execute(
                purposes.insert().values(
                    slug=purpose.slug.value,
                    description=purpose.description,
                    notice_version=purpose.notice_version.value,
                    notice_published_at=purpose.notice_published_at,
                    created_at=purpose.created_at,
                )
            )
        except IntegrityError as exc:
            raise PurposeExistsError from exc
        await self._record_notice(purpose)

    async def get(self, slug: PurposeSlug) -> Purpose | None:
        row = await self._conn.execute(select(purposes).where(purposes.c.slug == slug.value))
        found = row.mappings().first()
        return None if found is None else _to_purpose(found)

    async def all(self) -> list[Purpose]:
        rows = await self._conn.execute(select(purposes).order_by(purposes.c.slug))
        return [_to_purpose(r) for r in rows.mappings()]

    async def publish_notice(self, purpose: Purpose) -> None:
        await self._conn.execute(
            purposes.update()
            .where(purposes.c.slug == purpose.slug.value)
            .values(
                notice_version=purpose.notice_version.value,
                notice_published_at=purpose.notice_published_at,
            )
        )
        await self._record_notice(purpose)

    async def _record_notice(self, purpose: Purpose) -> None:
        await self._conn.execute(
            purpose_notices.insert().values(
                purpose=purpose.slug.value,
                notice_version=purpose.notice_version.value,
                published_at=purpose.notice_published_at,
            )
        )


def _to_purpose(row: RowMapping) -> Purpose:
    return Purpose(
        slug=PurposeSlug(row["slug"]),
        description=row["description"],
        notice_version=NoticeVersion(row["notice_version"]),
        notice_published_at=row["notice_published_at"],
        created_at=row["created_at"],
    )
