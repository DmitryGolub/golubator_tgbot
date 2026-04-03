from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.models.survey_session import SurveySession
    from src.models.user import User

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    func,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class AlertType(str, enum.Enum):
    low_score = "low_score"
    delta_decline = "delta_decline"
    cross_mismatch = "cross_mismatch"
    mentor_not_recommend = "mentor_not_recommend"


alert_type_enum = Enum(
    AlertType,
    name="alert_type_enum",
    schema="surveys",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class SurveyAlert(Base):
    __tablename__ = "survey_alerts"

    __table_args__ = {"schema": "surveys"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_type: Mapped[AlertType] = mapped_column(
        alert_type_enum,
        nullable=False,
    )
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("surveys.survey_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("iam.users.telegram_id", ondelete="SET NULL"),
        nullable=True,
    )
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    notified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    session: Mapped["SurveySession"] = relationship(
        "SurveySession",
        lazy="selectin",
    )
    student: Mapped[Optional["User"]] = relationship(
        "User",
        lazy="selectin",
    )
