from src.models.role import RoleModel
from src.services.auth import AuthService


async def get_user_role(user_id: int) -> RoleModel | None:
    return await AuthService.get_user_role(user_id)
