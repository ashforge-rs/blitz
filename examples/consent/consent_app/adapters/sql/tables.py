"""The consent store's tables.  ``migrations/`` creates exactly these (a test checks)."""

from sqlalchemy import Column, ForeignKey, Index, Integer, MetaData, String, Table

from .types import UtcDateTime

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

purposes = Table(
    "purposes",
    metadata,
    Column("slug", String(64), primary_key=True),
    Column("description", String(500), nullable=False),
    Column("notice_version", String(64), nullable=False),
    Column("notice_published_at", UtcDateTime, nullable=False),
    Column("created_at", UtcDateTime, nullable=False),
)

#: Every notice version a purpose ever had: what a subject was shown can always be shown again.
purpose_notices = Table(
    "purpose_notices",
    metadata,
    Column("purpose", String(64), ForeignKey("purposes.slug"), primary_key=True),
    Column("notice_version", String(64), primary_key=True),
    Column("published_at", UtcDateTime, nullable=False),
)

#: The ledger.  Append-only: database triggers (see migrations/) reject UPDATE and DELETE.
consent_events = Table(
    "consent_events",
    metadata,
    # Recording order (timestamps can tie); AUTOINCREMENT never reuses a value on SQLite.
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("id", String(64), nullable=False, unique=True),
    Column("subject_id", String(128), nullable=False),
    Column("purpose", String(64), ForeignKey("purposes.slug"), nullable=False),
    Column("decision", String(16), nullable=False),
    Column("notice_version", String(64)),
    Column("method", String(32)),
    Column("source", String(64), nullable=False),
    Column("recorded_by", String(64), nullable=False),
    Column("profile", String(32), nullable=False),
    Column("recorded_at", UtcDateTime, nullable=False),
    Index("ix_consent_events_subject_purpose", "subject_id", "purpose", "seq"),
    sqlite_autoincrement=True,
)
