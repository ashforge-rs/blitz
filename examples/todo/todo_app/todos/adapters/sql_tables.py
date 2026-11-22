"""The todos context's tables.  ``migrations/`` creates exactly these (a test checks)."""

from sqlalchemy import Boolean, Column, String, Table

from todo_app.persistence import UtcDateTime, context_metadata, idempotency_table, outbox_table

metadata = context_metadata()

#: ``owner_id`` has no foreign key into ``users``: each context owns its tables,
#: so either can move to its own database without the other noticing.
todos = Table(
    "todos",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("title", String(200), nullable=False),
    Column("done", Boolean(create_constraint=True, name="done_is_boolean"), nullable=False),
    Column("created_at", UtcDateTime, nullable=False),
)

audit_outbox = outbox_table(metadata, "todos_audit_outbox")
idempotency = idempotency_table(metadata, "todos_idempotency")
