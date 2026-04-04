from typing import Sequence

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from src.services.auth import AuthService


class PermissionFilter(BaseFilter):
    """Passes if the user has ANY of the required permissions (OR semantics).

    All current usages pass a single permission string. If AND semantics are
    needed, chain separate PermissionFilter instances or check permissions
    explicitly inside the handler.
    """

    def __init__(self, required: str | Sequence[str]):
        if isinstance(required, str):
            self.required = {required}
        else:
            self.required = set(required)

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        if not user:
            return False
        perms = await AuthService.get_user_permissions(user.id)
        return bool(self.required & perms)
