from typing import Sequence

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from src.services.auth import AuthService


class RoleFilter(BaseFilter):
    def __init__(self, allowed: Sequence[str]):
        self.allowed = set(allowed)

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        if not user:
            return False
        role = await AuthService.get_user_role(user.id)
        if not role:
            return False
        return role.name in self.allowed
