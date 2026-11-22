"""The users context's tables.  ``migrations/`` creates exactly these (a test checks)."""

from sqlalchemy import Column, ForeignKey, String, Table

from todo_app.persistence import UtcDateTime, context_metadata, idempotency_table, outbox_table

metadata = context_metadata()

users = Table(
    "users",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("email", String(254), nullable=False, unique=True),
    Column("name", String(100), nullable=False),
    Column("created_at", UtcDateTime, nullable=False),
)

#: Tokens live in their own table, so a user can hold several (rotation, revocation).
api_tokens = Table(
    "api_tokens",
    metadata,
    Column("token_hash", String(64), primary_key=True),
    Column(
        "user_id",
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("created_at", UtcDateTime, nullable=False),
)

audit_outbox = outbox_table(metadata, "users_audit_outbox")
idempotency = idempotency_table(metadata, "users_idempotency")

#: Named by the naming convention; Postgres reports it on a duplicate email.
EMAIL_UNIQUE = "uq_users_email"
