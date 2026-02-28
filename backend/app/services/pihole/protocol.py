"""Protocol definition for Pi-hole backend implementations."""

from __future__ import annotations

from typing import Protocol, Any


class PiholeBackend(Protocol):
    """Structural interface for Pi-hole backends.

    Implementations:
      - LocalDockerPiholeBackend: Pi-hole running as Docker container on the NAS
      - RemotePiholeBackend: External Pi-hole instance (e.g. Raspberry Pi)
      - DevPiholeBackend: Mock data for development
    """

    # ── Status & Summary ──────────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        """Return Pi-hole status including version, blocking state, container info."""
        ...

    async def get_summary(self) -> dict[str, Any]:
        """Return summary statistics (total queries, blocked, percentage, etc.)."""
        ...

    # ── Blocking Control ──────────────────────────────────────────────

    async def get_blocking(self) -> dict[str, Any]:
        """Return current blocking state."""
        ...

    async def set_blocking(self, enabled: bool, timer: int | None = None) -> dict[str, Any]:
        """Enable or disable blocking, optionally for a duration in seconds."""
        ...

    # ── Query Log ─────────────────────────────────────────────────────

    async def get_queries(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """Return paginated query log."""
        ...

    # ── Statistics ────────────────────────────────────────────────────

    async def get_top_domains(self, count: int = 10) -> dict[str, Any]:
        """Return top permitted domains."""
        ...

    async def get_top_blocked(self, count: int = 10) -> dict[str, Any]:
        """Return top blocked domains."""
        ...

    async def get_top_clients(self, count: int = 10) -> dict[str, Any]:
        """Return top clients by query count."""
        ...

    async def get_history(self) -> dict[str, Any]:
        """Return query history over time (for timeline chart)."""
        ...

    # ── Domain Management ─────────────────────────────────────────────

    async def get_domains(self, list_type: str, kind: str) -> dict[str, Any]:
        """Return domains from allow/deny lists.

        Args:
            list_type: 'allow' or 'deny'
            kind: 'exact' or 'regex'
        """
        ...

    async def add_domain(self, list_type: str, kind: str, domain: str, comment: str = "") -> dict[str, Any]:
        """Add a domain to allow/deny list."""
        ...

    async def remove_domain(self, list_type: str, kind: str, domain: str) -> dict[str, Any]:
        """Remove a domain from allow/deny list."""
        ...

    # ── Adlist Management ─────────────────────────────────────────────

    async def get_adlists(self) -> dict[str, Any]:
        """Return all configured adlists (blocklists)."""
        ...

    async def add_adlist(self, url: str, comment: str = "") -> dict[str, Any]:
        """Add a new adlist URL."""
        ...

    async def remove_adlist(self, address: str) -> dict[str, Any]:
        """Remove an adlist by its address URL."""
        ...

    async def toggle_adlist(self, address: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable an adlist by its address URL."""
        ...

    async def update_gravity(self) -> dict[str, Any]:
        """Trigger gravity database update (downloads blocklists)."""
        ...

    # ── Local DNS ─────────────────────────────────────────────────────

    async def get_local_dns(self) -> dict[str, Any]:
        """Return custom local DNS A-records."""
        ...

    async def add_local_dns(self, domain: str, ip: str) -> dict[str, Any]:
        """Add a custom local DNS A-record."""
        ...

    async def remove_local_dns(self, domain: str, ip: str) -> dict[str, Any]:
        """Remove a custom local DNS A-record."""
        ...

    # ── Actions ───────────────────────────────────────────────────────

    async def restart_dns(self) -> dict[str, Any]:
        """Restart the Pi-hole DNS resolver."""
        ...

    # ── Container Lifecycle (Docker backend only) ─────────────────────

    async def deploy_container(self, config: dict[str, Any]) -> dict[str, Any]:
        """Pull image and create/start the Pi-hole container."""
        ...

    async def start_container(self) -> dict[str, Any]:
        """Start an existing Pi-hole container."""
        ...

    async def stop_container(self) -> dict[str, Any]:
        """Stop the Pi-hole container."""
        ...

    async def remove_container(self) -> dict[str, Any]:
        """Remove the Pi-hole container."""
        ...

    async def update_container(self) -> dict[str, Any]:
        """Pull latest image and recreate the container."""
        ...

    async def get_container_logs(self, lines: int = 100) -> dict[str, Any]:
        """Return recent container log lines."""
        ...
