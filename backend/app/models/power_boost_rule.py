"""CPU boost allowlist rules — presence lifts the enforced cap."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class PowerBoostRule(Base):
    __tablename__ = "power_boost_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # process_glob | game_session
    pattern: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    target_max_mhz: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = full boost
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<PowerBoostRule(id={self.id}, kind='{self.kind}', label='{self.label}')>"
