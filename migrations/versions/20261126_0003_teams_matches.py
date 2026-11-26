"""teams, matches, external_refs jadvallari

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("competition", sa.String(length=16), nullable=False),
        sa.Column("season", sa.SmallInteger(), nullable=False),
        sa.Column("round", sa.String(length=64), nullable=True),
        sa.Column("home_team_id", sa.Integer(), nullable=False),
        sa.Column("away_team_id", sa.Integer(), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("minute", sa.SmallInteger(), nullable=True),
        sa.Column("home_score", sa.SmallInteger(), nullable=True),
        sa.Column("away_score", sa.SmallInteger(), nullable=True),
        sa.Column("home_penalties", sa.SmallInteger(), nullable=True),
        sa.Column("away_penalties", sa.SmallInteger(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["home_team_id"], ["teams.id"], name=op.f("fk_matches_home_team_id_teams")
        ),
        sa.ForeignKeyConstraint(
            ["away_team_id"], ["teams.id"], name=op.f("fk_matches_away_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_matches")),
    )
    op.create_index(op.f("ix_matches_kickoff_at"), "matches", ["kickoff_at"])
    op.create_table(
        "external_refs",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("entity", sa.String(length=16), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("internal_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("provider", "entity", "external_id", name=op.f("pk_external_refs")),
    )


def downgrade() -> None:
    op.drop_table("external_refs")
    op.drop_index(op.f("ix_matches_kickoff_at"), table_name="matches")
    op.drop_table("matches")
    op.drop_table("teams")
