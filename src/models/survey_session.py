from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.models.survey_template import SurveyQuestion, SurveyTemplate
    from src.models.user import User

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class SessionStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


session_status_enum = Enum(
    SessionStatus,
    name="session_status_enum",
    values_callable=lambda e: [m.value for m in e],
)


class SurveySession(Base):
    __tablename__ = "survey_sessions"

    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "respondent_id",
            "context_type",
            "context_id",
            name="uq_survey_session_unique",
        ),
        Index(
            "uq_survey_session_no_ctx",
            "template_id",
            "respondent_id",
            unique=True,
            postgresql_where=text("context_type IS NULL AND context_id IS NULL"),
        ),
        {"schema": "surveys"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("surveys.survey_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    respondent_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("iam.users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    context_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    context_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[SessionStatus] = mapped_column(
        session_status_enum,
        nullable=False,
        default=SessionStatus.pending,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    template: Mapped["SurveyTemplate"] = relationship(
        "SurveyTemplate",
        lazy="selectin",
    )
    respondent: Mapped["User"] = relationship(
        "User",
        lazy="selectin",
    )
    answers: Mapped[list["SurveyAnswer"]] = relationship(
        "SurveyAnswer",
        back_populates="session",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class SurveyAnswer(Base):
    __tablename__ = "survey_answers"

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "question_id",
            name="uq_survey_answer_unique",
        ),
        {"schema": "surveys"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("surveys.survey_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("surveys.survey_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    value_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_int: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    value_choice: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    session: Mapped["SurveySession"] = relationship(
        "SurveySession",
        back_populates="answers",
    )
    question: Mapped["SurveyQuestion"] = relationship(
        "SurveyQuestion",
        lazy="selectin",
    )
