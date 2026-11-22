"""Table builders shared by the contexts: each context owns its own copies."""

from sqlalchemy import JSON, Column, Integer, MetaData, PrimaryKeyConstraint, String, Table

from .types import UtcDateTime

#: Deterministic constraint names on every dialect, so migrations can refer to them.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def context_metadata() -> MetaData:
    return MetaData(naming_convention=NAMING_CONVENTION)


def outbox_table(metadata: MetaData, name: str) -> Table:
    """Audit entries committed with their change, waiting for the relay."""
    return Table(
        name,
        metadata,
        # AUTOINCREMENT on SQLite: ids are never reused, so delivery order is stable.
        Column("seq", Integer, primary_key=True, autoincrement=True),
        Column("id", String(64), nullable=False, unique=True),
        Column("operation", String(100), nullable=False),
        Column("outcome", String(20), nullable=False),
        Column("resource_id", String(64)),
        Column("user_id", String(64)),
        Column("correlation_id", String(64), nullable=False),
        Column("client_address", String(100)),
        Column("entrypoint", String(200)),
        Column("details", JSON, nullable=False),
        Column("occurred_at", UtcDateTime, nullable=False),
        sqlite_autoincrement=True,
    )


def idempotency_table(metadata: MetaData, name: str) -> Table:
    """Completed requests by (scope, key): the primary key is what makes retries safe."""
    return Table(
        name,
        metadata,
        Column("scope", String(200), nullable=False),
        Column("key", String(255), nullable=False),
        Column("request_fingerprint", String(64), nullable=False),
        Column("resource_id", String(64), nullable=False),
        Column("secret_ref", String(64)),
        Column("created_at", UtcDateTime, nullable=False),
        PrimaryKeyConstraint("scope", "key"),
    )
