"""Energy price configuration model."""

from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EnergyPriceConfig(Base):
    """
    Singleton configuration for energy price calculations.

    Only one row should exist (id=1) containing the current price settings.
    """
    __tablename__ = "energy_price_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cost_per_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.40)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="EUR")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<EnergyPriceConfig(cost={self.cost_per_kwh} {self.currency})>"
