"""Database model for cloud export jobs."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class CloudExportJob(Base):
    """Cloud export job — uploads a NAS file/folder to a cloud provider and creates a sharing link."""

    __tablename__ = "cloud_export_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cloud_connections.id", ondelete="CASCADE"), nullable=False
    )

    # Source (NAS)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_directory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Destination (Cloud)
    cloud_folder: Mapped[str] = mapped_column(
        String(500), nullable=False, default="BaluHost Shares/"
    )
    cloud_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Sharing
    share_link: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    link_type: Mapped[str] = mapped_column(String(20), nullable=False, default="view")
    link_password: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | uploading | creating_link | ready | failed | revoked
    progress_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<CloudExportJob(id={self.id}, status='{self.status}', file='{self.file_name}')>"

    def is_expired(self) -> bool:
        """Check if the export link has expired."""
        if self.expires_at is None:
            return False
        expires = self.expires_at
        # SQLite returns naive datetimes even for timezone=True columns; normalise.
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires
