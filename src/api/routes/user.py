from datetime import datetime
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError

from src.api.schemas.user import TagCreateRequest, TagResponse, UserResponse
from src.dao.tag import TagDAO
from src.dao.user import UserDAO
from src.models.user import State

router = APIRouter(tags=["users"])


def _parse_enum_value(raw: str | None, enum_cls: type[Enum]):
    if raw is None:
        return None
    try:
        return enum_cls[raw]
    except KeyError:
        pass
    try:
        return enum_cls(raw)
    except ValueError as exc:
        allowed_values = ", ".join(item.name for item in enum_cls)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Некорректное значение '{raw}'. Допустимые: {allowed_values}",
        ) from exc


@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(payload: TagCreateRequest) -> TagResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Имя тега не может быть пустым",
        )
    try:
        tag = await TagDAO.add(name=name)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Тег с таким именем уже существует",
        ) from exc
    return TagResponse(id=tag.id, name=tag.name)


@router.post("/users/{telegram_id}/tags/{tag_id}", response_model=UserResponse)
async def assign_tag_to_user(telegram_id: int, tag_id: int) -> UserResponse:
    user = await UserDAO.assign_tag(telegram_id=telegram_id, tag_id=tag_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь или тег не найден",
        )
    return UserResponse(
        telegram_id=user.telegram_id,
        username=user.username,
        name=user.name,
        role=user.role_rel.name if user.role_rel else None,
        state=user.state.name if user.state else None,
        registered_at=user.registered_at,
        tags=[TagResponse(id=tag.id, name=tag.name) for tag in user.tags],
    )


@router.delete("/users/{telegram_id}/tags/{tag_id}", response_model=UserResponse)
async def unassign_tag_from_user(telegram_id: int, tag_id: int) -> UserResponse:
    user = await UserDAO.unassign_tag(telegram_id=telegram_id, tag_id=tag_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    return UserResponse(
        telegram_id=user.telegram_id,
        username=user.username,
        name=user.name,
        role=user.role_rel.name if user.role_rel else None,
        state=user.state.name if user.state else None,
        registered_at=user.registered_at,
        tags=[TagResponse(id=tag.id, name=tag.name) for tag in user.tags],
    )


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    role: Annotated[str | None, Query(description="role name/value")] = None,
    state: Annotated[str | None, Query(description="state name/value")] = None,
    tag_id: Annotated[int | None, Query(description="ID тега")] = None,
    registered_from: Annotated[datetime | None, Query(description="Дата регистрации от")] = None,
    registered_to: Annotated[datetime | None, Query(description="Дата регистрации до")] = None,
) -> list[UserResponse]:
    if registered_from and registered_to and registered_from > registered_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="registered_from не может быть больше registered_to",
        )

    users = await UserDAO.get_all(
        role_name=role,
        state=_parse_enum_value(state, State),
        tag_id=tag_id,
        registered_from=registered_from,
        registered_to=registered_to,
    )
    return [
        UserResponse(
            telegram_id=user.telegram_id,
            username=user.username,
            name=user.name,
            role=user.role_rel.name if user.role_rel else None,
            state=user.state.name if user.state else None,
            registered_at=user.registered_at,
            tags=[TagResponse(id=tag.id, name=tag.name) for tag in user.tags],
        )
        for user in users
    ]
