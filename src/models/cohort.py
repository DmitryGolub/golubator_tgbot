from typing import List
from sqlalchemy import String, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base



class Cohort(Base):
    __tablename__ = "cohorts"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )

    name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    users: Mapped[List["User"]] = relationship(
        "User", back_populates="cohort", passive_deletes=True, lazy="selectin",
    )
