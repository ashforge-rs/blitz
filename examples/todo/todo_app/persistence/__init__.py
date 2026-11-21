"""SQL infrastructure shared by the contexts' adapters (SQLAlchemy Core, async)."""

from .database import Database
from .migrations import SchemaOutOfDateError, alembic_config, ensure_at_head, upgrade
from .outbox_relay import OutboxRelay, to_audit_event
from .sql_audit_outbox import SqlAuditOutbox
from .sql_idempotency_store import SqlIdempotencyStore
from .tables import context_metadata, idempotency_table, outbox_table
from .types import UtcDateTime

__all__ = [
    "Database",
    "OutboxRelay",
    "SchemaOutOfDateError",
    "SqlAuditOutbox",
    "SqlIdempotencyStore",
    "UtcDateTime",
    "alembic_config",
    "context_metadata",
    "ensure_at_head",
    "idempotency_table",
    "outbox_table",
    "to_audit_event",
    "upgrade",
]
