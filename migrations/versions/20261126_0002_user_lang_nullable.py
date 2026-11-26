"""users.lang: til tanlanmaguncha NULL

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "lang", existing_type=sa.String(length=8), nullable=True)
    # Shu paytgacha til avtomatik qo'yilgan, uni hech kim o'zi tanlamagan —
    # mavjud foydalanuvchilar ham keyingi xabarida til tanlaydi.
    op.execute("UPDATE users SET lang = NULL")


def downgrade() -> None:
    op.execute("UPDATE users SET lang = 'uz' WHERE lang IS NULL")
    op.alter_column("users", "lang", existing_type=sa.String(length=8), nullable=False)
