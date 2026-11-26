"""notifications jadvali va matches'dagi eslatma belgilari

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("pre_notified_at", sa.DateTime(timezone=True)))
    op.add_column("matches", sa.Column("result_notified_at", sa.DateTime(timezone=True)))
    # Shu paytgacha tugagan o'yinlar natijasi haqida xabar yuborilmaydi.
    op.execute("UPDATE matches SET result_notified_at = now() WHERE status = 'finished'")

    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=True),
        sa.Column("day", sa.Date(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "send_after",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_notifications_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("user_id", "dedupe_key", name=op.f("uq_notifications_user_id")),
    )
    op.create_index(
        "ix_notifications_pending",
        "notifications",
        ["send_after"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_pending", table_name="notifications")
    op.drop_table("notifications")
    op.drop_column("matches", "result_notified_at")
    op.drop_column("matches", "pre_notified_at")
