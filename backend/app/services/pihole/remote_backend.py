"""Remote Pi-hole backend — connects to an external Pi-hole instance via API only."""

from __future__ import annotations

import logging
from typing import Any

from app.services.pihole.api_client import PiholeApiClient
from app.services.pihole.docker_backend import LocalDockerPiholeBackend

logger = logging.getLogger(__name__)


class RemotePiholeBackend(LocalDockerPiholeBackend):
    """Backend for an external Pi-hole instance (e.g. Raspberry Pi).

    Inherits all API methods from LocalDockerPiholeBackend but disables
    container lifecycle operations since the container is not managed locally.
    """

    def __init__(self, pihole_url: str, password: str) -> None:
        # Skip parent __init__ to avoid ContainerManager
        self._api = PiholeApiClient(pihole_url, password)
        self._pihole_url = pihole_url
        self._password = password

    async def close(self) -> None:
        """Clean up resources."""
        await self._api.close()

    # ── Override status to reflect remote mode ────────────────────────

    async def get_status(self) -> dict[str, Any]:
        connected = await self._api.is_connected()
        version = None
        blocking_enabled = False

        if connected:
            version = await self._api.get_version()
            try:
                blocking_data = await self._api.get_blocking()
                blocking_enabled = blocking_data.get("blocking") == "enabled"
            except Exception:
                pass

        return {
            "mode": "remote",
            "connected": connected,
            "blocking_enabled": blocking_enabled,
            "version": version,
            "container_running": None,  # Not applicable for remote
            "container_status": None,
            "uptime": None,
        }

    # ── Container operations are not available in remote mode ─────────

    async def deploy_container(self, config: dict[str, Any]) -> dict[str, Any]:
        return {"success": False, "message": "Container management not available in remote mode"}

    async def start_container(self) -> dict[str, Any]:
        return {"success": False, "message": "Container management not available in remote mode"}

    async def stop_container(self) -> dict[str, Any]:
        return {"success": False, "message": "Container management not available in remote mode"}

    async def remove_container(self) -> dict[str, Any]:
        return {"success": False, "message": "Container management not available in remote mode"}

    async def update_container(self) -> dict[str, Any]:
        return {"success": False, "message": "Container management not available in remote mode"}

    async def get_container_logs(self, lines: int = 100) -> dict[str, Any]:
        return {"logs": "", "lines": 0, "message": "Container logs not available in remote mode"}
