from src.core.dao import BaseDAO
from src.models.tag import Tag


class TagDAO(BaseDAO):
    model = Tag
