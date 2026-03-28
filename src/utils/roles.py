from src.models.user import User


def _has_permission(user: User, codename: str) -> bool:
    if not user.role_rel:
        return False
    return any(p.codename == codename for p in user.role_rel.permissions)


def is_admin(user: User) -> bool:
    return _has_permission(user, "all_permissions")


def is_mentor(user: User) -> bool:
    return _has_permission(user, "mentor_role")
