"""
SQLAlchemy model for power consumption samples.

Stores historical power consumption data for long-term analysis and statistics.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import Base


class PowerSample(Base):
    """
    Power consumption sample from a Tapo device.

    Stores individual power measurements for historical analysis,
    trend detection, and energy usage statistics.
    """

    __tablename__ = "power_samples"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("tapo_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)

    # Power measurements
    watts = Column(Float, nullable=False)
    voltage = Column(Float, nullable=True)
    current = Column(Float, nullable=True)
    energy_today = Column(Float, nullable=True)

    # Online/offline status
    is_online = Column(Boolean, nullable=False, default=True)

    # Relationships
    device = relationship("TapoDevice", back_populates="power_samples")

    def __repr__(self) -> str:
        return f"<PowerSample(device_id={self.device_id}, watts={self.watts}, timestamp={self.timestamp})>"
