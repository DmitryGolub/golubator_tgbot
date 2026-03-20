from datetime import datetime

from pydantic import BaseModel


class TagCreateRequest(BaseModel):
    name: str


class TagResponse(BaseModel):
    id: int
    name: str


class UserResponse(BaseModel):
    telegram_id: int
    username: str
    name: str
    role: str
    state: str | None
    registered_at: datetime
    tags: list[TagResponse]
