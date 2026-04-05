from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class LeadSourceType(str, enum.Enum):
    referral = "referral"
    channel = "channel"


class LeadSource(Base):
    __tablename__ = "lead_sources"
    __table_args__ = {"schema": "iam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(
        Enum(LeadSourceType, name="lead_source_type_enum", schema="iam")
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
