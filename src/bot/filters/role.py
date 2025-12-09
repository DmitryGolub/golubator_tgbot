from typing import Sequence
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from src.utils.auth import get_user_role
from src.models.user import Role


class RoleFilter(BaseFilter):
    def __init__(self, allowed: Sequence[Role]):
        self.allowed = set(allowed)

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user

        role = await get_user_role(user.id)

        return role in self.allowed
