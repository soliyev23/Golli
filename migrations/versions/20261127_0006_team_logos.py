"""teams: logotip havolasi va maxsus emoji identifikatori

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("logo_url", sa.String(length=255), nullable=True))
    op.add_column("teams", sa.Column("emoji_id", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("teams", "emoji_id")
    op.drop_column("teams", "logo_url")
