"""NFS export configuration model."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class NfsExport(Base):
    """A single admin-defined, host-based NFS export."""

    __tablename__ = "nfs_exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Path relative to the storage root; "" means the storage root itself.
    path: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    # Single client spec: IPv4, IPv4/CIDR, hostname, or "*".
    clients: Mapped[str] = mapped_column(String(255), nullable=False)
    read_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    root_squash: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    def __repr__(self) -> str:
        return f"<NfsExport(id={self.id}, path='{self.path}', clients='{self.clients}')>"
