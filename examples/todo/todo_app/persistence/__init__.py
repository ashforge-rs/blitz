"""SQL infrastructure shared by the contexts' adapters (SQLAlchemy Core, async)."""

from .context_runtime import ContextRuntime, open_context_runtime
from .database import Database
from .migrations import ContextMigrations, SchemaOutOfDateError, alembic_config
from .outbox_relay import Backlog, OutboxRelay, to_audit_event
from .sql_audit_outbox import SqlAuditOutbox
from .sql_idempotency_store import SqlIdempotencyStore
from .sql_unit_of_work import SqlUnitOfWork
from .tables import context_metadata, idempotency_table, outbox_table
from .types import UtcDateTime

__all__ = [
    "Backlog",
    "ContextMigrations",
    "ContextRuntime",
    "Database",
    "OutboxRelay",
    "SchemaOutOfDateError",
    "SqlAuditOutbox",
    "SqlIdempotencyStore",
    "SqlUnitOfWork",
    "UtcDateTime",
    "alembic_config",
    "context_metadata",
    "idempotency_table",
    "open_context_runtime",
    "outbox_table",
    "to_audit_event",
]
