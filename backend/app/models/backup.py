"""Backup database model."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Integer, BigInteger, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class Backup(Base):
    """Backup model for tracking system backups."""
    
    __tablename__ = "backups"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    filepath: Mapped[str] = mapped_column(String(1000), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    backup_type: Mapped[str] = mapped_column(String(20), nullable=False, default="full")
    # full, incremental, database_only, files_only
    
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress", index=True)
    # in_progress, completed, failed
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    creator_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata about what's included
    includes_database: Mapped[bool] = mapped_column(nullable=False, default=True)
    includes_files: Mapped[bool] = mapped_column(nullable=False, default=True)
    includes_config: Mapped[bool] = mapped_column(nullable=False, default=False)
    
    __table_args__ = (
        Index('idx_backup_status_created', 'status', 'created_at'),
        Index('idx_backup_creator_created', 'creator_id', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return f"<Backup(id={self.id}, filename='{self.filename}', status='{self.status}')>"
