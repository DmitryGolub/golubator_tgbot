from src.core.dao import BaseDAO
from src.models.user import User


class UserDAO(BaseDAO):
    model = User
