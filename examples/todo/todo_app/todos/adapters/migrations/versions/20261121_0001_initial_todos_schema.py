"""initial todos schema

Revision ID: 0001
Revises: (none)
Create Date: 2026-11-21 23:46:06.502763
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
        "todos",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "done", sa.Boolean(create_constraint=True, name="done_is_boolean"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_todos")),
    )
    op.create_index(op.f("ix_todos_owner_id"), "todos", ["owner_id"], unique=False)

    op.create_table(
        "todos_audit_outbox",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("client_address", sa.String(length=100), nullable=True),
        sa.Column("entrypoint", sa.String(length=200), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("seq", name=op.f("pk_todos_audit_outbox")),
        sa.UniqueConstraint("id", name=op.f("uq_todos_audit_outbox_id")),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "todos_idempotency",
        sa.Column("scope", sa.String(length=200), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=False),
        sa.Column("secret_ref", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("scope", "key", name=op.f("pk_todos_idempotency")),
    )


def downgrade() -> None:
    op.drop_table("todos_idempotency")
    op.drop_table("todos_audit_outbox")
    op.drop_index(op.f("ix_todos_owner_id"), table_name="todos")

    op.drop_table("todos")
