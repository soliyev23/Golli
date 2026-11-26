"""favorites jadvali

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "favorites",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_favorites_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_favorites_team_id_teams")),
        sa.PrimaryKeyConstraint("user_id", "team_id", name=op.f("pk_favorites")),
    )
    op.create_index(op.f("ix_favorites_team_id"), "favorites", ["team_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_favorites_team_id"), table_name="favorites")
    op.drop_table("favorites")
