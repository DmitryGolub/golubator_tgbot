from src.models.user import User


def is_mentor(user: User) -> bool:
    return bool(user.role_rel and user.role_rel.is_mentor)


def is_student(user: User) -> bool:
    return bool(user.role_rel and user.role_rel.is_student)


def is_admin(user: User) -> bool:
    return bool(user.role_rel and user.role_rel.name == "admin")
