from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from src.models.user import User

from src.core.database import Base


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        Integer,
        ForeignKey("iam.roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        Integer,
        ForeignKey("iam.permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    schema="iam",
)


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = {"schema": "iam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codename: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)

    roles: Mapped[list["RoleModel"]] = relationship(
        "RoleModel",
        secondary=role_permissions,
        back_populates="permissions",
        lazy="selectin",
    )


class RoleModel(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "iam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_mentor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_student: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    permissions: Mapped[list[Permission]] = relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
        lazy="selectin",
    )
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="role_rel", lazy="noload"
    )
