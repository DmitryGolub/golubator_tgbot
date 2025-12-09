from typing import Optional

from src.models.user import Role
from src.dao.user import UserDAO


async def get_user_role(user_id: int) -> Optional[Role]:
    user = await UserDAO.find_one_or_none(telegram_id=user_id)

    if not user:
        return None

    return user.role
