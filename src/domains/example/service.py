from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from loguru import logger
from opentelemetry import trace
from returns.result import Failure, Result, Success

from audit.backend import (
    AuditBackend,
    AuditEvent,
    AuditEventType,
    AuditIntegrity,
    AuditResult,
    AuditSeverity,
)
from service import Service

from .errors import ItemError, ItemErrorCode
from .models import CreateItemRequest, Item, UpdateItemRequest

if TYPE_CHECKING:
    from context import RequestContext

    from .repository import ItemRepository

_tracer = trace.get_tracer("domains.example", schema_url="https://opentelemetry.io/schemas/1.11.0")


class ItemService(Service):
    """
    Business logic for the *items* bounded context.

    Return contract (TigerBeetle / Result monad)
    ---------------------------------------------
    Every method returns ``Result[T, ItemError]`` — never raises for domain
    errors, never returns bare ``None``.  The ``Ok`` / ``Err`` variants are
    explicit at the call site; callers must handle both branches.

    ``as_result(Exception)`` converts unexpected storage/IO exceptions into
    ``Failure(ItemError(STORAGE_ERROR, …))`` so nothing escapes as an unhandled
    exception from the service layer.

    SOC 2 compliance surface
    ------------------------
    CC6  — Logical Access Controls:
        ``created_by`` / ``updated_by`` provenance recorded from the
        authenticated principal in ``ctx``.

    CC7  — System Operations & Monitoring:
        Each method opens an OpenTelemetry span; exceptions are recorded and
        the span is marked ERROR so OTLP backends surface anomalies.

    CC8  — Change Management:
        Every state-changing operation emits a structured
        :class:`~audit.backend.AuditEvent` — including failures.

    CC9  — Risk Mitigation:
        Storage failures are converted to ``Err`` and a FAILURE audit event
        is emitted; nothing is silently swallowed.
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
        *,
        operation: str,
        result: AuditResult,
        item_id: str | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        metadata: dict[str, object] = {"operation": operation}
        if item_id:
            metadata["item_id"] = item_id
        if extra:
            metadata.update(extra)

        event = AuditEvent(
            event_type=AuditEventType.ADMIN_ACTION,
            severity=AuditSeverity.WARNING if result != AuditResult.SUCCESS else AuditSeverity.INFO,
            result=result,
            principal=self._principal(ctx),
            remote_addr=ctx.remote_addr,
            correlation_id=ctx.request_id,
            method=operation,
            path=ctx.path,
            metadata=metadata,
        )
        self._integrity.add_integrity(event)
        await self._audit.log(event)

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
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))
                logger.error("item.get.error", item_id=item_id, error=str(exc))
                return Failure(ItemError(ItemErrorCode.STORAGE_ERROR, str(exc), item_id))

            if item is None:
                span.set_attribute("item.found", False)
                logger.debug("item.get.not_found", item_id=item_id, request_id=ctx.request_id)
                return Failure(
                    ItemError(ItemErrorCode.NOT_FOUND, f"{item_id!r} not found", item_id)
                )

            span.set_attribute("item.found", True)
            logger.debug("item.get", item_id=item_id, request_id=ctx.request_id)
            return Success(item)

    async def list_all(self, ctx: RequestContext) -> Result[list[Item], ItemError]:
        with _tracer.start_as_current_span(
            "example.items.list_all",
            attributes={"request.id": ctx.request_id},
        ) as span:
            try:
                items = await self._repo.find_all()
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))
                logger.error("item.list_all.error", error=str(exc))
                return Failure(ItemError(ItemErrorCode.STORAGE_ERROR, str(exc)))

            span.set_attribute("items.count", len(items))
            logger.debug("item.list_all", count=len(items), request_id=ctx.request_id)
            return Success(items)

    # ------------------------------------------------------------------
    # Write operations — each emits an audit event (CC8)
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
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))
                logger.error(
                    "item.create.error",
                    name=request.name,
                    error=str(exc),
                    request_id=ctx.request_id,
                )
                await self._emit(
                    ctx,
                    operation="items.create",
                    result=AuditResult.FAILURE,
                    extra={"error": str(exc), "item_name": request.name},
                )
                return Failure(ItemError(ItemErrorCode.STORAGE_ERROR, str(exc)))

            ctx.set("last_created_item_id", saved.id)
            span.set_attribute("item.id", saved.id)
            logger.info(
                "item.created",
                item_id=saved.id,
                name=saved.name,
                principal=self._principal(ctx),
                request_id=ctx.request_id,
            )
            await self._emit(
                ctx,
                operation="items.create",
                result=AuditResult.SUCCESS,
                item_id=saved.id,
                extra={"item_name": saved.name},
            )
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
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))
                logger.error("item.update.error", item_id=item_id, error=str(exc))
                await self._emit(
                    ctx,
                    operation="items.update",
                    result=AuditResult.FAILURE,
                    item_id=item_id,
                    extra={"error": str(exc)},
                )
                return Failure(ItemError(ItemErrorCode.STORAGE_ERROR, str(exc), item_id))

            if item is None:
                span.set_attribute("item.found", False)
                return Failure(
                    ItemError(ItemErrorCode.NOT_FOUND, f"{item_id!r} not found", item_id)
                )

            updated = item.model_copy(
                update={
                    k: v
                    for k, v in {
                        "name": request.name,
                        "data": request.data,
                    }.items()
                    if v is not None
                }
                | {
                    "updated_at": datetime.now(UTC),
                    "updated_by": self._principal(ctx),
                }
            )
            try:
                saved = await self._repo.save(updated)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))
                logger.error("item.update.save_error", item_id=item_id, error=str(exc))
                await self._emit(
                    ctx,
                    operation="items.update",
                    result=AuditResult.FAILURE,
                    item_id=item_id,
                    extra={"error": str(exc)},
                )
                return Failure(ItemError(ItemErrorCode.STORAGE_ERROR, str(exc), item_id))

            ctx.set("last_updated_item_id", item_id)
            span.set_attribute("item.found", True)
            logger.info(
                "item.updated",
                item_id=item_id,
                principal=self._principal(ctx),
                request_id=ctx.request_id,
            )
            await self._emit(
                ctx,
                operation="items.update",
                result=AuditResult.SUCCESS,
                item_id=item_id,
            )
            return Success(saved)

    async def delete(self, item_id: str, ctx: RequestContext) -> Result[None, ItemError]:
        with _tracer.start_as_current_span(
            "example.items.delete",
            attributes={"item.id": item_id, "request.id": ctx.request_id},
        ) as span:
            try:
                deleted = await self._repo.delete(item_id)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))
                logger.error("item.delete.error", item_id=item_id, error=str(exc))
                await self._emit(
                    ctx,
                    operation="items.delete",
                    result=AuditResult.FAILURE,
                    item_id=item_id,
                    extra={"error": str(exc)},
                )
                return Failure(ItemError(ItemErrorCode.STORAGE_ERROR, str(exc), item_id))

            span.set_attribute("item.deleted", deleted)
            if not deleted:
                logger.debug("item.delete.not_found", item_id=item_id, request_id=ctx.request_id)
                return Failure(
                    ItemError(ItemErrorCode.NOT_FOUND, f"{item_id!r} not found", item_id)
                )

            ctx.set("last_deleted_item_id", item_id)
            logger.info(
                "item.deleted",
                item_id=item_id,
                principal=self._principal(ctx),
                request_id=ctx.request_id,
            )
            await self._emit(
                ctx,
                operation="items.delete",
                result=AuditResult.SUCCESS,
                item_id=item_id,
            )
            return Success(None)
