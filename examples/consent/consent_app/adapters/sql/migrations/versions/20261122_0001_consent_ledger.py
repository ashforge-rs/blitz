"""consent ledger

Revision ID: 0001
Revises: (none)
Create Date: 2026-11-22 00:25:01.665185
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "purposes",
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("notice_version", sa.String(length=64), nullable=False),
        sa.Column("notice_published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("slug", name=op.f("pk_purposes")),
    )
    op.create_table(
        "consent_events",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("notice_version", sa.String(length=64), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("recorded_by", sa.String(length=64), nullable=False),
        sa.Column("profile", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["purpose"], ["purposes.slug"], name=op.f("fk_consent_events_purpose_purposes")
        ),
        sa.PrimaryKeyConstraint("seq", name=op.f("pk_consent_events")),
        sa.UniqueConstraint("id", name=op.f("uq_consent_events_id")),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_consent_events_subject_purpose",
        "consent_events",
        ["subject_id", "purpose", "seq"],
        unique=False,
    )

    op.create_table(
        "purpose_notices",
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("notice_version", sa.String(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["purpose"], ["purposes.slug"], name=op.f("fk_purpose_notices_purpose_purposes")
        ),
        sa.PrimaryKeyConstraint("purpose", "notice_version", name=op.f("pk_purpose_notices")),
    )

    _make_ledger_append_only()


def downgrade() -> None:
    _drop_append_only_guard()
    op.drop_table("purpose_notices")
    op.drop_index("ix_consent_events_subject_purpose", table_name="consent_events")

    op.drop_table("consent_events")
    op.drop_table("purposes")


# The ledger is evidence: once written, an event may never change or disappear.
# Enforced in the database, so no code path (or SQL console) can rewrite history.
_GUARD_MESSAGE = "consent_events is append-only"


def _make_ledger_append_only() -> None:
    if op.get_bind().dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER consent_events_no_{action.lower()} BEFORE {action} "
                f"ON consent_events BEGIN SELECT RAISE(ABORT, '{_GUARD_MESSAGE}'); END"
            )
    else:
        op.execute(
            "CREATE FUNCTION consent_events_append_only() RETURNS trigger LANGUAGE plpgsql "
            f"AS $$ BEGIN RAISE EXCEPTION '{_GUARD_MESSAGE}'; END $$"
        )
        op.execute(
            "CREATE TRIGGER consent_events_append_only BEFORE UPDATE OR DELETE "
            "ON consent_events FOR EACH ROW EXECUTE FUNCTION consent_events_append_only()"
        )


def _drop_append_only_guard() -> None:
    if op.get_bind().dialect.name == "sqlite":
        for action in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS consent_events_no_{action}")
    else:
        op.execute("DROP TRIGGER IF EXISTS consent_events_append_only ON consent_events")
        op.execute("DROP FUNCTION IF EXISTS consent_events_append_only()")
