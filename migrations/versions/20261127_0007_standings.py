"""standings: turnir jadvallari

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "standings",
        sa.Column("competition", sa.String(length=16), nullable=False),
        sa.Column("season", sa.SmallInteger(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("group_name", sa.String(length=64), nullable=True),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("played", sa.SmallInteger(), nullable=False),
        sa.Column("wins", sa.SmallInteger(), nullable=False),
        sa.Column("draws", sa.SmallInteger(), nullable=False),
        sa.Column("losses", sa.SmallInteger(), nullable=False),
        sa.Column("goals_for", sa.SmallInteger(), nullable=False),
        sa.Column("goals_against", sa.SmallInteger(), nullable=False),
        sa.Column("points", sa.SmallInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_standings_team_id_teams"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("competition", "season", "team_id", name=op.f("pk_standings")),
    )


def downgrade() -> None:
    op.drop_table("standings")
