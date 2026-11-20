import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from loguru import logger
from opentelemetry import trace
from returns.result import Failure, Result, Success

from audit.backend import AuditBackend, AuditIntegrity, AuditResult
from audit.helpers import log_operation
from service import Service

from .errors import ItemError, ItemErrorCode
from .models import CreateItemRequest, Item, UpdateItemRequest

if TYPE_CHECKING:
    from opentelemetry.trace import Span

    from context import RequestContext

    from .repository import ItemRepository

_tracer = trace.get_tracer("domains.example", schema_url="https://opentelemetry.io/schemas/1.11.0")


class ItemService(Service):
    """
    Business logic for the *items* bounded context.

    Every method returns ``Result[T, ItemError]`` and opens an OpenTelemetry
    span.  Storage exceptions are caught at the repository call and converted by
    :meth:`_storage_failure`, which records them on the span, logs them and (for
    writes) emits a FAILURE audit event.  Successful writes are audited too.
    """

    def __init__(
        self,
        repository: ItemRepository,
        audit_backend: AuditBackend,
        audit_integrity: AuditIntegrity,
    ) -> None:
        self._repo = repository
        self._audit = audit_backend
        self._integrity = audit_integrity

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _principal(self, ctx: RequestContext) -> str | None:
        return cast("str | None", ctx.get("principal"))

    async def _emit(
        self,
        ctx: RequestContext,
        operation: str,
        *,
        result: AuditResult = AuditResult.SUCCESS,
        item_id: str | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        await log_operation(
            self._audit,
            self._integrity,
            ctx,
            operation,
            result=result,
            resource_id=item_id,
            extra_metadata=extra,
        )

    async def _storage_failure(
        self,
        exc: Exception,
        ctx: RequestContext,
        span: Span,
        operation: str,
        *,
        item_id: str | None = None,
        audit: bool = True,
        extra: dict[str, object] | None = None,
    ) -> Failure[ItemError]:
        """Record a storage exception everywhere it must go; return the Failure."""
        span.record_exception(exc)
        span.set_status(trace.StatusCode.ERROR, str(exc))
        logger.error(
            f"{operation}.error", item_id=item_id, error=str(exc), request_id=ctx.request_id
        )
        if audit:
            await self._emit(
                ctx,
                operation,
                result=AuditResult.FAILURE,
                item_id=item_id,
                extra={"error": str(exc), **(extra or {})},
            )
        return Failure(ItemError(ItemErrorCode.STORAGE_ERROR, str(exc), item_id))

    @staticmethod
    def _not_found(item_id: str) -> Failure[ItemError]:
        return Failure(ItemError(ItemErrorCode.NOT_FOUND, f"{item_id!r} not found", item_id))

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get(self, item_id: str, ctx: RequestContext) -> Result[Item, ItemError]:
        with _tracer.start_as_current_span(
            "example.items.get",
            attributes={"item.id": item_id, "request.id": ctx.request_id},
        ) as span:
            try:
                item = await self._repo.find_by_id(item_id)
            except Exception as exc:  # noqa: BLE001 — storage boundary: any backend error → STORAGE_ERROR
                return await self._storage_failure(
                    exc, ctx, span, "items.get", item_id=item_id, audit=False
                )

            span.set_attribute("item.found", item is not None)
            if item is None:
                return self._not_found(item_id)
            return Success(item)

    async def list_all(self, ctx: RequestContext) -> Result[list[Item], ItemError]:
        with _tracer.start_as_current_span(
            "example.items.list_all",
            attributes={"request.id": ctx.request_id},
        ) as span:
            try:
                items = await self._repo.find_all()
            except Exception as exc:  # noqa: BLE001 — storage boundary: any backend error → STORAGE_ERROR
                return await self._storage_failure(exc, ctx, span, "items.list_all", audit=False)

            span.set_attribute("items.count", len(items))
            return Success(items)

    # ------------------------------------------------------------------
    # Write operations — each emits an audit event
    # ------------------------------------------------------------------

    async def create(
        self, request: CreateItemRequest, ctx: RequestContext
    ) -> Result[Item, ItemError]:
        with _tracer.start_as_current_span(
            "example.items.create",
            attributes={"item.name": request.name, "request.id": ctx.request_id},
        ) as span:
            item = Item(
                id=str(uuid.uuid4()),
                name=request.name,
                data=request.data,
                created_by=self._principal(ctx),
                updated_by=self._principal(ctx),
            )
            try:
                saved = await self._repo.save(item)
            except Exception as exc:  # noqa: BLE001 — storage boundary: any backend error → STORAGE_ERROR
                return await self._storage_failure(
                    exc, ctx, span, "items.create", extra={"item_name": request.name}
                )

            ctx.set("last_created_item_id", saved.id)
            span.set_attribute("item.id", saved.id)
            logger.info("item.created", item_id=saved.id, request_id=ctx.request_id)
            await self._emit(ctx, "items.create", item_id=saved.id, extra={"item_name": saved.name})
            return Success(saved)

    async def update(
        self, item_id: str, request: UpdateItemRequest, ctx: RequestContext
    ) -> Result[Item, ItemError]:
        with _tracer.start_as_current_span(
            "example.items.update",
            attributes={"item.id": item_id, "request.id": ctx.request_id},
        ) as span:
            try:
                item = await self._repo.find_by_id(item_id)
                if item is None:
                    span.set_attribute("item.found", False)
                    return self._not_found(item_id)

                changes = request.model_dump(exclude_none=True)
                updated = item.model_copy(
                    update=changes
                    | {"updated_at": datetime.now(UTC), "updated_by": self._principal(ctx)}
                )
                saved = await self._repo.save(updated)
            except Exception as exc:  # noqa: BLE001 — storage boundary: any backend error → STORAGE_ERROR
                return await self._storage_failure(exc, ctx, span, "items.update", item_id=item_id)

            ctx.set("last_updated_item_id", item_id)
            span.set_attribute("item.found", True)
            logger.info("item.updated", item_id=item_id, request_id=ctx.request_id)
            await self._emit(ctx, "items.update", item_id=item_id)
            return Success(saved)

    async def delete(self, item_id: str, ctx: RequestContext) -> Result[None, ItemError]:
        with _tracer.start_as_current_span(
            "example.items.delete",
            attributes={"item.id": item_id, "request.id": ctx.request_id},
        ) as span:
            try:
                deleted = await self._repo.delete(item_id)
            except Exception as exc:  # noqa: BLE001 — storage boundary: any backend error → STORAGE_ERROR
                return await self._storage_failure(exc, ctx, span, "items.delete", item_id=item_id)

            span.set_attribute("item.deleted", deleted)
            if not deleted:
                return self._not_found(item_id)

            ctx.set("last_deleted_item_id", item_id)
            logger.info("item.deleted", item_id=item_id, request_id=ctx.request_id)
            await self._emit(ctx, "items.delete", item_id=item_id)
            return Success(None)
