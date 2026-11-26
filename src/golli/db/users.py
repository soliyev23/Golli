from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from golli.db.models import User


async def get_or_create_user(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        # ON CONFLICT: bir foydalanuvchidan ikki xabar bir vaqtda kelsa ham xato bermaydi.
        await session.execute(
            insert(User).values(id=user_id).on_conflict_do_nothing(index_elements=["id"])
        )
        user = await session.get(User, user_id)
    assert user is not None
    return user
