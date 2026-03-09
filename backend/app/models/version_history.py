"""Version history model for tracking all versions that have run on this system."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class VersionHistory(Base):
    """Tracks every version+commit combination that has ever started on this system.

    Unlike UpdateHistory (which tracks deliberate update operations), this model
    records a row for every distinct (version, git_commit) pair seen at startup.
    Repeated starts of the same build increment times_started and update last_seen.
    """

    __tablename__ = "version_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    git_commit: Mapped[str] = mapped_column(String(40), nullable=False)
    git_commit_short: Mapped[str] = mapped_column(String(10), nullable=False)
    git_branch: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    python_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    times_started: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
    )

    __table_args__ = (
        UniqueConstraint("version", "git_commit", name="uq_version_commit"),
    )

    def __repr__(self) -> str:
        return (
            f"<VersionHistory(id={self.id}, version='{self.version}', "
            f"commit='{self.git_commit_short}', starts={self.times_started})>"
        )
