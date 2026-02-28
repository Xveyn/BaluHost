"""Disabled backend for Pi-hole — returns null/empty data for all methods.

Used when Pi-hole mode is "disabled" in production to avoid showing mock data.
"""

from __future__ import annotations

from typing import Any

_DISABLED_MSG = "Pi-hole is disabled"


class DisabledPiholeBackend:
    """Backend that returns empty/null responses for all Pi-hole operations.

    Ensures the frontend receives clearly-disabled data instead of mock statistics.
    """

    # ── Status & Summary ──────────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        return {
            "mode": "disabled",
            "connected": False,
            "blocking_enabled": False,
            "version": None,
            "container_running": False,
            "container_status": None,
            "uptime": None,
        }

    async def get_summary(self) -> dict[str, Any]:
        return {
            "total_queries": 0,
            "blocked_queries": 0,
            "percent_blocked": 0,
            "unique_domains": 0,
            "forwarded_queries": 0,
            "cached_queries": 0,
            "clients_seen": 0,
            "gravity_size": 0,
            "gravity_last_updated": None,
        }

    # ── Blocking Control ──────────────────────────────────────────────

    async def get_blocking(self) -> dict[str, Any]:
        return {"blocking": "disabled", "timer": None}

    async def set_blocking(self, enabled: bool, timer: int | None = None) -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG, "blocking": "disabled", "timer": None}

    # ── Query Log ─────────────────────────────────────────────────────

    async def get_queries(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return {"queries": [], "total": 0}

    # ── Statistics ────────────────────────────────────────────────────

    async def get_top_domains(self, count: int = 10) -> dict[str, Any]:
        return {"top_permitted": []}

    async def get_top_blocked(self, count: int = 10) -> dict[str, Any]:
        return {"top_blocked": []}

    async def get_top_clients(self, count: int = 10) -> dict[str, Any]:
        return {"top_clients": []}

    async def get_history(self) -> dict[str, Any]:
        return {"history": []}

    # ── Domain Management ─────────────────────────────────────────────

    async def get_domains(self, list_type: str, kind: str) -> dict[str, Any]:
        return {"domains": []}

    async def add_domain(self, list_type: str, kind: str, domain: str, comment: str = "") -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    async def remove_domain(self, list_type: str, kind: str, domain: str) -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    # ── Adlist Management ─────────────────────────────────────────────

    async def get_adlists(self) -> dict[str, Any]:
        return {"lists": []}

    async def add_adlist(self, url: str, comment: str = "") -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    async def remove_adlist(self, address: str) -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    async def toggle_adlist(self, address: str, enabled: bool) -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    async def update_gravity(self) -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    # ── Local DNS ─────────────────────────────────────────────────────

    async def get_local_dns(self) -> dict[str, Any]:
        return {"records": []}

    async def add_local_dns(self, domain: str, ip: str) -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    async def remove_local_dns(self, domain: str, ip: str) -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    # ── Actions ───────────────────────────────────────────────────────

    async def restart_dns(self) -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    # ── Container Lifecycle ───────────────────────────────────────────

    async def deploy_container(self, config: dict[str, Any]) -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    async def start_container(self) -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    async def stop_container(self) -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    async def remove_container(self) -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    async def update_container(self) -> dict[str, Any]:
        return {"success": False, "message": _DISABLED_MSG}

    async def get_container_logs(self, lines: int = 100) -> dict[str, Any]:
        return {"logs": "", "lines": 0}
