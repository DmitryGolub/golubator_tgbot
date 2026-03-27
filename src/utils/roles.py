from src.models.user import User


def is_admin(user: User) -> bool:
    return bool(user.role_rel and user.role_rel.name == "admin")
