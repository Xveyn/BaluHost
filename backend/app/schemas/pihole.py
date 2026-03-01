"""Pydantic schemas for Pi-hole DNS integration."""

from datetime import datetime
from typing import Any, Optional, Union
from pydantic import BaseModel, Field


# ── Status & Summary ──────────────────────────────────────────────────

class PiholeStatusResponse(BaseModel):
    """Pi-hole overall status."""
    mode: str = Field(..., description="Backend mode: docker | remote | disabled | dev")
    connected: bool = Field(..., description="Whether the Pi-hole API is reachable")
    blocking_enabled: bool = Field(False, description="Whether DNS blocking is active")
    version: Optional[Any] = Field(None, description="Pi-hole FTL version (string or dict)")
    container_running: Optional[bool] = Field(None, description="Docker container running (docker mode only)")
    container_status: Optional[str] = Field(None, description="Docker container status string")
    uptime: Optional[int] = Field(None, description="Pi-hole uptime in seconds")

class PiholeSummaryResponse(BaseModel):
    """Summary statistics."""
    total_queries: int = 0
    blocked_queries: int = 0
    percent_blocked: float = 0.0
    unique_domains: int = 0
    forwarded_queries: int = 0
    cached_queries: int = 0
    clients_seen: int = 0
    gravity_size: int = 0
    gravity_last_updated: Optional[Union[str, int]] = None

# ── Blocking ──────────────────────────────────────────────────────────

class BlockingRequest(BaseModel):
    """Request to enable/disable DNS blocking."""
    enabled: bool = Field(..., description="True to enable, False to disable")
    timer: Optional[int] = Field(None, ge=0, le=86400, description="Auto-reenable after N seconds (max 24h)")

class BlockingResponse(BaseModel):
    """Current blocking state."""
    blocking: str = Field(..., description="enabled | disabled | unknown")
    timer: Optional[int] = Field(None, description="Seconds until auto-reenable (null if permanent)")

# ── Query Log ─────────────────────────────────────────────────────────

class QueryEntry(BaseModel):
    """Single DNS query log entry."""
    timestamp: float = 0
    domain: str = ""
    client: str = ""
    query_type: str = ""
    status: str = ""
    reply_type: str = ""
    response_time: float = 0

class QueryLogResponse(BaseModel):
    """Paginated query log."""
    queries: list[QueryEntry] = []
    total: int = 0

# ── Statistics ────────────────────────────────────────────────────────

class DomainEntry(BaseModel):
    """Domain with hit count."""
    domain: str
    count: int

class ClientEntry(BaseModel):
    """Client with query count."""
    client: str
    name: Optional[str] = None
    count: int

class TopDomainsResponse(BaseModel):
    """Top domains response."""
    top_permitted: list[DomainEntry] = []

class TopBlockedResponse(BaseModel):
    """Top blocked domains response."""
    top_blocked: list[DomainEntry] = []

class TopClientsResponse(BaseModel):
    """Top clients response."""
    top_clients: list[ClientEntry] = []

class HistoryEntry(BaseModel):
    """Single history data point."""
    timestamp: float
    total: int = 0
    blocked: int = 0

class HistoryResponse(BaseModel):
    """Query history timeline."""
    history: list[HistoryEntry] = []

# ── Domain Management ─────────────────────────────────────────────────

class DomainListEntry(BaseModel):
    """Domain in allow/deny list."""
    id: Optional[int] = None
    domain: str
    comment: Optional[str] = ""
    enabled: bool = True
    date_added: Optional[Union[str, int]] = None
    date_modified: Optional[Union[str, int]] = None

class DomainListResponse(BaseModel):
    """Domain list response."""
    domains: list[DomainListEntry] = []

class AddDomainRequest(BaseModel):
    """Request to add a domain to allow/deny list."""
    domain: str = Field(..., min_length=1, max_length=253, description="Domain name or regex pattern")
    list_type: str = Field(..., pattern="^(allow|deny)$", description="allow or deny")
    kind: str = Field(..., pattern="^(exact|regex)$", description="exact or regex")
    comment: str = Field("", max_length=500, description="Optional comment")

class RemoveDomainRequest(BaseModel):
    """Request to remove a domain from allow/deny list."""
    domain: str = Field(..., min_length=1, max_length=253)
    list_type: str = Field(..., pattern="^(allow|deny)$")
    kind: str = Field(..., pattern="^(exact|regex)$")

# ── Adlist Management ─────────────────────────────────────────────────

class AdlistEntry(BaseModel):
    """Adlist (blocklist) entry."""
    id: Optional[int] = None
    url: str
    comment: Optional[str] = ""
    enabled: bool = True
    number: int = 0
    date_added: Optional[Union[str, int]] = None
    date_modified: Optional[Union[str, int]] = None

class AdlistResponse(BaseModel):
    """Adlist listing response."""
    lists: list[AdlistEntry] = []

class AddAdlistRequest(BaseModel):
    """Request to add an adlist."""
    url: str = Field(..., min_length=1, max_length=2000, description="Blocklist URL")
    comment: str = Field("", max_length=500, description="Optional comment")

class ToggleAdlistRequest(BaseModel):
    """Request to enable/disable an adlist."""
    address: str = Field(..., min_length=1, max_length=2000, description="Adlist URL")
    enabled: bool = Field(..., description="True to enable, False to disable")

class RemoveAdlistRequest(BaseModel):
    """Request to remove an adlist."""
    address: str = Field(..., min_length=1, max_length=2000, description="Adlist URL")

# ── Local DNS ─────────────────────────────────────────────────────────

class LocalDnsEntry(BaseModel):
    """Custom local DNS A-record."""
    domain: str
    ip: str

class LocalDnsResponse(BaseModel):
    """Local DNS records."""
    records: list[LocalDnsEntry] = []

class AddLocalDnsRequest(BaseModel):
    """Request to add a local DNS record."""
    domain: str = Field(..., min_length=1, max_length=253, description="Domain name")
    ip: str = Field(..., min_length=7, max_length=45, description="IPv4 or IPv6 address")

class RemoveLocalDnsRequest(BaseModel):
    """Request to remove a local DNS record."""
    domain: str = Field(..., min_length=1, max_length=253)
    ip: str = Field(..., min_length=7, max_length=45, description="IPv4 or IPv6 address")

# ── Container Management ──────────────────────────────────────────────

class ContainerDeployRequest(BaseModel):
    """Request to deploy the Pi-hole Docker container."""
    image_tag: str = Field("latest", max_length=100, description="Docker image tag")
    web_port: int = Field(8053, ge=1024, le=65535, description="Web UI port on host")
    upstream_dns: str = Field("1.1.1.1;1.0.0.1", max_length=500, description="Upstream DNS servers, semicolon-separated")
    timezone: str = Field("Europe/Berlin", max_length=100, description="Container timezone")

class ContainerActionResponse(BaseModel):
    """Response from a container action."""
    success: bool
    message: str
    container_status: Optional[str] = None


class ContainerDeployResponse(ContainerActionResponse):
    """Deploy response – includes one-time password."""
    password: Optional[str] = Field(None, description="Generated admin password (shown once)")

class ContainerLogsResponse(BaseModel):
    """Container log output."""
    logs: str = ""
    lines: int = 0

# ── Configuration ─────────────────────────────────────────────────────

class PiholeConfigResponse(BaseModel):
    """Current Pi-hole configuration from database."""
    mode: str = "disabled"
    pihole_url: Optional[str] = None
    upstream_dns: str = "1.1.1.1;1.0.0.1"
    docker_image_tag: str = "latest"
    web_port: int = 8053
    use_as_vpn_dns: bool = True
    remote_pihole_url: Optional[str] = None
    health_check_interval: int = 30
    failover_active: bool = False
    last_failover_at: Optional[datetime] = None
    has_password: bool = False
    has_remote_password: bool = False
    # DNS settings
    dns_dnssec: bool = False
    dns_rev_server: Optional[str] = None
    dns_rate_limit_count: int = 1000
    dns_rate_limit_interval: int = 60
    dns_domain_needed: bool = False
    dns_bogus_priv: bool = True
    dns_domain_name: str = "lan"
    dns_expand_hosts: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class PiholeConfigUpdateRequest(BaseModel):
    """Request to update Pi-hole configuration."""
    mode: Optional[str] = Field(None, pattern="^(docker|remote|disabled)$", description="Operating mode")
    pihole_url: Optional[str] = Field(None, max_length=500, description="Pi-hole URL for remote mode")
    password: Optional[str] = Field(None, min_length=1, max_length=500, description="Pi-hole API password (will be encrypted)")
    upstream_dns: Optional[str] = Field(None, max_length=500, description="Upstream DNS servers")
    docker_image_tag: Optional[str] = Field(None, max_length=100, description="Docker image tag")
    web_port: Optional[int] = Field(None, ge=1024, le=65535, description="Web UI port")
    use_as_vpn_dns: Optional[bool] = Field(None, description="Use Pi-hole as VPN DNS")
    remote_pihole_url: Optional[str] = Field(None, max_length=500, description="Remote Pi-hole URL (e.g. http://192.168.1.50:80)")
    remote_password: Optional[str] = Field(None, min_length=1, max_length=500, description="Remote Pi-hole API password (will be encrypted)")
    health_check_interval: Optional[int] = Field(None, ge=10, le=300, description="Health check interval in seconds")
    # DNS settings
    dns_dnssec: Optional[bool] = Field(None, description="Enable DNSSEC validation")
    dns_rev_server: Optional[str] = Field(None, max_length=500, description="Conditional forwarding (e.g. true,192.168.178.0/24,192.168.178.1,fritz.box)")
    dns_rate_limit_count: Optional[int] = Field(None, ge=0, le=100000, description="Rate limit: max queries per interval")
    dns_rate_limit_interval: Optional[int] = Field(None, ge=0, le=86400, description="Rate limit: interval in seconds")
    dns_domain_needed: Optional[bool] = Field(None, description="Never forward non-FQDN A and AAAA queries")
    dns_bogus_priv: Optional[bool] = Field(None, description="Never forward reverse lookups for private IP ranges")
    dns_domain_name: Optional[str] = Field(None, max_length=100, description="Local domain name")
    dns_expand_hosts: Optional[bool] = Field(None, description="Expand hostnames by adding domain name")

# ── Failover ─────────────────────────────────────────────────────────

class FailoverStatusResponse(BaseModel):
    """Active/passive failover status."""
    remote_configured: bool = Field(..., description="Whether a remote Pi-hole URL is configured")
    remote_connected: bool = Field(..., description="Whether the remote Pi-hole is currently reachable")
    failover_active: bool = Field(..., description="True if NAS is handling DNS (Pi offline)")
    active_source: str = Field(..., description="'remote' or 'local'")
    remote_url: Optional[str] = Field(None, description="Remote Pi-hole URL")
    last_failover_at: Optional[datetime] = Field(None, description="Last failover/failback timestamp")


# ── Stored Queries (PostgreSQL) ──────────────────────────────────────

class StoredQueryEntry(BaseModel):
    """DNS query stored in PostgreSQL."""
    id: int
    timestamp: datetime
    domain: str
    client: str
    query_type: str
    status: str
    reply_type: Optional[str] = None
    response_time_ms: Optional[float] = None

    model_config = {"from_attributes": True}

class StoredQueryResponse(BaseModel):
    """Paginated stored query response."""
    queries: list[StoredQueryEntry] = []
    total: int = 0
    page: int = 1
    page_size: int = 100

class StoredStatsResponse(BaseModel):
    """Aggregated stats for a time period."""
    total_queries: int = 0
    blocked_queries: int = 0
    cached_queries: int = 0
    forwarded_queries: int = 0
    unique_domains: int = 0
    unique_clients: int = 0
    avg_response_time_ms: Optional[float] = None
    block_rate: float = 0.0
    period: str = "24h"

class StoredDomainEntry(BaseModel):
    """Domain with count from stored data."""
    domain: str
    count: int

class StoredClientEntry(BaseModel):
    """Client with count from stored data."""
    client: str
    count: int

class StoredTopDomainsResponse(BaseModel):
    """Top domains from stored data."""
    top_domains: list[StoredDomainEntry] = []
    period: str = "24h"

class StoredTopBlockedResponse(BaseModel):
    """Top blocked domains from stored data."""
    top_blocked: list[StoredDomainEntry] = []
    period: str = "24h"

class StoredTopClientsResponse(BaseModel):
    """Top clients from stored data."""
    top_clients: list[StoredClientEntry] = []
    period: str = "24h"

class HourlyCountEntry(BaseModel):
    """Single hourly data point."""
    hour: datetime
    total_queries: int = 0
    blocked_queries: int = 0
    cached_queries: int = 0
    forwarded_queries: int = 0

    model_config = {"from_attributes": True}

class StoredHistoryResponse(BaseModel):
    """Hourly timeline from stored data."""
    history: list[HourlyCountEntry] = []
    period: str = "24h"

# ── Query Collector ──────────────────────────────────────────────────

class QueryCollectorStatusResponse(BaseModel):
    """Collector service status."""
    running: bool = False
    is_enabled: bool = True
    last_poll_at: Optional[datetime] = None
    total_queries_stored: int = 0
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    poll_interval_seconds: int = 30
    retention_days: int = 30

class QueryCollectorConfigUpdate(BaseModel):
    """Update collector configuration."""
    is_enabled: Optional[bool] = Field(None, description="Enable/disable the collector")
    poll_interval_seconds: Optional[int] = Field(None, ge=10, le=300, description="Poll interval in seconds")
    retention_days: Optional[int] = Field(None, ge=1, le=365, description="Data retention in days")
