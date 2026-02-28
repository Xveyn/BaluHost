"""Database model for Pi-hole configuration (singleton)."""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text

from app.models.base import Base


class PiholeConfig(Base):
    """Singleton configuration for Pi-hole DNS integration.

    Only one row should exist (id=1). Use get_or_create pattern.
    """
    __tablename__ = "pihole_config"

    id = Column(Integer, primary_key=True, default=1)
    mode = Column(String(20), nullable=False, default="disabled")  # docker | remote | disabled
    pihole_url = Column(String(500), nullable=True)  # For remote mode (e.g. http://192.168.1.100:8053)
    password_encrypted = Column(Text, nullable=True)  # Fernet-encrypted Pi-hole API password
    upstream_dns = Column(String(500), nullable=False, default="1.1.1.1;1.0.0.1")
    docker_image_tag = Column(String(100), nullable=False, default="latest")
    web_port = Column(Integer, nullable=False, default=8053)
    use_as_vpn_dns = Column(Boolean, nullable=False, default=True)

    # Remote Pi-hole (Primary when configured)
    remote_pihole_url = Column(String(500), nullable=True)  # e.g. "http://192.168.1.50:80"
    remote_password_encrypted = Column(Text, nullable=True)  # Fernet-encrypted

    # Failover state
    failover_active = Column(Boolean, nullable=False, default=False)  # True = Pi offline, NAS takes over
    health_check_interval = Column(Integer, nullable=False, default=30)  # seconds
    last_failover_at = Column(DateTime, nullable=True)  # last failover/failback timestamp

    # DNS settings (deployed as FTLCONF_* env vars)
    dns_dnssec = Column(Boolean, nullable=False, default=False)
    dns_rev_server = Column(String(500), nullable=True)  # "true,192.168.178.0/24,192.168.178.1,fritz.box"
    dns_rate_limit_count = Column(Integer, nullable=False, default=1000)
    dns_rate_limit_interval = Column(Integer, nullable=False, default=60)
    dns_domain_needed = Column(Boolean, nullable=False, default=False)
    dns_bogus_priv = Column(Boolean, nullable=False, default=True)
    dns_domain_name = Column(String(100), nullable=False, default="lan")
    dns_expand_hosts = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
