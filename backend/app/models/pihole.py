"""Database model for Pi-hole configuration (singleton)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class PiholeConfig(Base):
    """Singleton configuration for Pi-hole DNS integration.

    Only one row should exist (id=1). Use get_or_create pattern.
    """
    __tablename__ = "pihole_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="disabled")  # docker | remote | disabled
    pihole_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # For remote mode (e.g. http://192.168.1.100:8053)
    password_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Fernet-encrypted Pi-hole API password
    upstream_dns: Mapped[str] = mapped_column(String(500), nullable=False, default="1.1.1.1;1.0.0.1")
    docker_image_tag: Mapped[str] = mapped_column(String(100), nullable=False, default="latest")
    web_port: Mapped[int] = mapped_column(Integer, nullable=False, default=8053)
    use_as_vpn_dns: Mapped[bool] = mapped_column(nullable=False, default=True)

    # Remote Pi-hole (Primary when configured)
    remote_pihole_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # e.g. "http://192.168.1.50:80"
    remote_password_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Fernet-encrypted

    # Failover state
    failover_active: Mapped[bool] = mapped_column(nullable=False, default=False)  # True = Pi offline, NAS takes over
    health_check_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=30)  # seconds
    last_failover_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # last failover/failback timestamp

    # DNS settings (deployed as FTLCONF_* env vars)
    dns_dnssec: Mapped[bool] = mapped_column(nullable=False, default=False)
    dns_rev_server: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # "true,192.168.178.0/24,192.168.178.1,fritz.box"
    dns_rate_limit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    dns_rate_limit_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    dns_domain_needed: Mapped[bool] = mapped_column(nullable=False, default=False)
    dns_bogus_priv: Mapped[bool] = mapped_column(nullable=False, default=True)
    dns_domain_name: Mapped[str] = mapped_column(String(100), nullable=False, default="lan")
    dns_expand_hosts: Mapped[bool] = mapped_column(nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
