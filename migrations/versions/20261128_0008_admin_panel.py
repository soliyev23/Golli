"""admin panel: foydalanuvchi profili, oxirgi faollik va ulashish havolalari

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invite_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invite_links")),
        sa.UniqueConstraint("code", name=op.f("uq_invite_links_code")),
    )
    op.add_column("users", sa.Column("first_name", sa.String(length=128)))
    op.add_column("users", sa.Column("last_name", sa.String(length=128)))
    op.add_column("users", sa.Column("username", sa.String(length=64)))
    op.add_column("users", sa.Column("language_code", sa.String(length=16)))
    op.add_column("users", sa.Column("last_seen_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("invite_link_id", sa.Integer()))
    op.create_foreign_key(
        op.f("fk_users_invite_link_id_invite_links"),
        "users",
        "invite_links",
        ["invite_link_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_last_seen_at", "users", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_users_last_seen_at", table_name="users")
    op.drop_constraint(op.f("fk_users_invite_link_id_invite_links"), "users", type_="foreignkey")
    for column in (
        "invite_link_id",
        "last_seen_at",
        "language_code",
        "username",
        "last_name",
        "first_name",
    ):
        op.drop_column("users", column)
    op.drop_table("invite_links")
