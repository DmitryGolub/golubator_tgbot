from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.models.role import RoleModel

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class QuestionType(str, enum.Enum):
    text = "text"
    rating = "rating"
    single_choice = "single_choice"
    multiple_choice = "multiple_choice"


question_type_enum = Enum(
    QuestionType,
    name="question_type_enum",
    values_callable=lambda e: [m.value for m in e],
)


class SurveyTemplate(Base):
    __tablename__ = "survey_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_role_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    questions: Mapped[list["SurveyQuestion"]] = relationship(
        "SurveyQuestion",
        back_populates="template",
        lazy="selectin",
        order_by="SurveyQuestion.sort_order",
        cascade="all, delete-orphan",
    )
    target_role: Mapped[Optional["RoleModel"]] = relationship(
        "RoleModel",
        lazy="selectin",
    )


class SurveyQuestion(Base):
    __tablename__ = "survey_questions"

    __table_args__ = (
        UniqueConstraint("template_id", "sort_order", name="uq_survey_question_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("survey_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(
        question_type_enum,
        nullable=False,
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    template: Mapped["SurveyTemplate"] = relationship(
        "SurveyTemplate",
        back_populates="questions",
    )
    options: Mapped[list["SurveyQuestionOption"]] = relationship(
        "SurveyQuestionOption",
        back_populates="question",
        lazy="selectin",
        order_by="SurveyQuestionOption.sort_order",
        cascade="all, delete-orphan",
    )


class SurveyQuestionOption(Base):
    __tablename__ = "survey_question_options"

    __table_args__ = (
        UniqueConstraint("question_id", "sort_order", name="uq_survey_option_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("survey_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)

    question: Mapped["SurveyQuestion"] = relationship(
        "SurveyQuestion",
        back_populates="options",
    )
