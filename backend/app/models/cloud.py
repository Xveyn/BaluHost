"""Database models for cloud import/sync."""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class CloudOAuthConfig(Base):
    """Stored OAuth credentials (client_id + secret) per cloud provider, per user."""
    __tablename__ = "cloud_oauth_configs"
    __table_args__ = (UniqueConstraint("provider", "user_id", name="uq_cloud_oauth_provider_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # google_drive | onedrive
    encrypted_client_id: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_client_secret: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<CloudOAuthConfig(id={self.id}, provider='{self.provider}')>"


class CloudConnection(Base):
    """Stored cloud provider connections per user."""
    __tablename__ = "cloud_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # google_drive | onedrive | icloud
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    rclone_remote_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    encrypted_config: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet-encrypted credentials
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CloudConnection(id={self.id}, provider='{self.provider}', user_id={self.user_id})>"


class CloudImportJob(Base):
    """Cloud import/sync job records."""
    __tablename__ = "cloud_import_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    connection_id: Mapped[int] = mapped_column(Integer, ForeignKey("cloud_connections.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)  # Path in cloud
    destination_path: Mapped[str] = mapped_column(String(1000), nullable=False)  # Path on NAS
    job_type: Mapped[str] = mapped_column(String(20), nullable=False)  # import | sync
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | running | completed | failed | cancelled
    progress_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    files_transferred: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_file: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<CloudImportJob(id={self.id}, status='{self.status}', type='{self.job_type}')>"
