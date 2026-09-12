"""Datenbankmodell für den geplanten Systemneustart.

Eine einzige Zeile (id=1). Bewusst getrennt von `scheduler_configs.extra_config`
(dort steht, was der Admin gesetzt hat — hier, wo der Automat steht) und von
`scheduler_executions` (dieser Zustand wird beim Boot in `lifespan` gelesen,
bevor irgendein Scheduler-Code läuft).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ScheduledRebootState(Base):
    """Singleton-Zustand des Neustart-Automaten (id=1)."""

    __tablename__ = "scheduled_reboot_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    phase: Mapped[str] = mapped_column(
        String(24), nullable=False, default="idle", server_default="idle"
    )
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Wiederholungssperre. Ohne sie erkennt der Automat nach dem Neustart
    # denselben Termin erneut als fällig und startet in einer Schleife neu.
    last_completed_due_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Die Box wurde für diesen Termin aus dem Suspend geholt; nur dann wird
    # nach dem Neustart wieder suspendiert.
    woke_for_reboot: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # Der vom Termin verdrängte reguläre Weckzeitpunkt. NULL ist gültig und
    # bedeutet „suspendieren ohne RTC-Alarm".
    resuspend_wake_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    execution_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_skip_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    warned_for_due_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    phase_entered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ScheduledRebootState(phase={self.phase}, due_at={self.due_at})>"
