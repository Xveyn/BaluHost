"""Pi-hole service orchestrator — selects and manages the active backend."""

from __future__ import annotations

import logging
import socket
import time
from collections.abc import Awaitable
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.pihole import PiholeConfig
from app.services.monitoring.shm import SHM_DIR, read_shm, write_shm
from app.services.vpn_encryption import VPNEncryption

logger = logging.getLogger(__name__)

# Module-level backend singleton (NAS local / dev)
_backend: Any = None
_backend_mode: Optional[str] = None
_backend_created_at: float = 0.0

# SHM file for cross-worker deploy invalidation
PIHOLE_DEPLOY_TS_FILE = "pihole_deploy_ts.json"

# Module-level remote API client singleton
_remote_api: Any = None
_remote_url: Optional[str] = None

# Failover health tracking (in-memory, not persisted)
_fail_count: int = 0
_FAIL_THRESHOLD: int = 3


def _create_backend(mode: str, pihole_url: str = "", password: str = "", web_port: int = 8053) -> Any:
    """Create a backend instance based on mode."""
    if mode == "docker":
        from app.services.pihole.docker_backend import LocalDockerPiholeBackend
        url = pihole_url or f"http://localhost:{web_port}"
        return LocalDockerPiholeBackend(url, password)
    elif mode == "remote":
        from app.services.pihole.remote_backend import RemotePiholeBackend
        if not pihole_url:
            raise ValueError("pihole_url is required for remote mode")
        return RemotePiholeBackend(pihole_url, password)
    elif mode == "dev":
        from app.services.pihole.dev_backend import DevPiholeBackend
        return DevPiholeBackend()
    else:
        # "disabled" or any unknown mode → return null-data backend
        from app.services.pihole.disabled_backend import DisabledPiholeBackend
        return DisabledPiholeBackend()


def _reset_remote_api() -> None:
    """Reset the cached remote API client."""
    global _remote_api, _remote_url
    if _remote_api is not None:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_safe_close(_remote_api))
            else:
                loop.run_until_complete(_safe_close(_remote_api))
        except Exception:
            pass
    _remote_api = None
    _remote_url = None


class PiholeService:
    """High-level Pi-hole service used by API routes.

    Manages backend lifecycle and provides a unified interface.
    Supports active-passive failover between a remote Pi-hole (primary)
    and the local NAS Pi-hole (secondary).
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Configuration ─────────────────────────────────────────────────

    def get_config(self) -> PiholeConfig:
        """Get or create the singleton Pi-hole config row."""
        config = self._db.query(PiholeConfig).filter(PiholeConfig.id == 1).first()
        if config is None:
            config = PiholeConfig(id=1, mode="disabled")
            self._db.add(config)
            self._db.commit()
            self._db.refresh(config)
        return config

    def update_config(self, **kwargs: Any) -> PiholeConfig:
        """Update Pi-hole configuration fields."""
        config = self.get_config()
        password_plain = kwargs.pop("password", None)
        remote_password_plain = kwargs.pop("remote_password", None)

        for key, value in kwargs.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)

        # Handle clearing remote_pihole_url explicitly
        if "remote_pihole_url" in kwargs and kwargs["remote_pihole_url"] is None:
            config.remote_pihole_url = None
            config.remote_password_encrypted = None
            config.failover_active = False

        # Encrypt local password if provided
        if password_plain:
            try:
                config.password_encrypted = VPNEncryption.encrypt_key(password_plain)
            except ValueError:
                logger.warning("VPN_ENCRYPTION_KEY not set — storing password hash placeholder")
                config.password_encrypted = None

        # Encrypt remote password if provided
        if remote_password_plain:
            try:
                config.remote_password_encrypted = VPNEncryption.encrypt_key(remote_password_plain)
            except ValueError:
                logger.warning("VPN_ENCRYPTION_KEY not set — cannot encrypt remote password")
                config.remote_password_encrypted = None

        self._db.commit()
        self._db.refresh(config)

        # Reset backends so they pick up new config
        global _backend, _backend_mode
        if _backend is not None:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(_safe_close(_backend))
                else:
                    loop.run_until_complete(_safe_close(_backend))
            except Exception:
                pass
        _backend = None
        _backend_mode = None

        # Reset remote API if URL changed
        _reset_remote_api()

        return config

    # ── Backend Access ────────────────────────────────────────────────

    def _get_backend(self) -> Any:
        """Get or create the active backend based on current config."""
        global _backend, _backend_mode, _backend_created_at

        config = self.get_config()
        effective_mode = config.mode

        # Dev mode override
        if settings.is_dev_mode or getattr(settings, "pihole_force_dev_backend", False):
            effective_mode = "dev"

        # Check if another worker deployed a new container
        deploy_data = read_shm(PIHOLE_DEPLOY_TS_FILE, max_age_seconds=86400)
        if deploy_data and deploy_data.get("ts", 0) > _backend_created_at:
            logger.info("Pi-hole backend invalidated by deploy signal (deploy_ts=%.1f > created_at=%.1f)",
                        deploy_data["ts"], _backend_created_at)
            _backend = None

        # Reuse existing backend if mode hasn't changed
        if _backend is not None and _backend_mode == effective_mode:
            return _backend

        # Close old backend
        if _backend is not None:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(_safe_close(_backend))
                else:
                    loop.run_until_complete(_safe_close(_backend))
            except Exception:
                pass

        # Decrypt password
        password = ""
        if config.password_encrypted:
            try:
                password = VPNEncryption.decrypt_key(config.password_encrypted)
            except Exception:
                logger.warning("Failed to decrypt Pi-hole password")

        _backend = _create_backend(effective_mode, config.pihole_url or "", password, config.web_port)
        _backend_mode = effective_mode
        _backend_created_at = time.time()
        logger.info("Pi-hole backend initialized: %s", effective_mode)
        return _backend

    @property
    def backend(self) -> Any:
        """Shortcut property to get the current backend."""
        return self._get_backend()

    # ── Remote API (for failover) ─────────────────────────────────────

    def _get_remote_api(self) -> Any:
        """Get or create the remote Pi-hole API client."""
        global _remote_api, _remote_url
        from app.services.pihole.api_client import PiholeApiClient

        config = self.get_config()
        url = config.remote_pihole_url

        if not url:
            return None

        # Reuse if URL hasn't changed
        if _remote_api is not None and _remote_url == url:
            return _remote_api

        # Close old client
        _reset_remote_api()

        # Decrypt remote password
        password = ""
        if config.remote_password_encrypted:
            try:
                password = VPNEncryption.decrypt_key(config.remote_password_encrypted)
            except Exception:
                logger.warning("Failed to decrypt remote Pi-hole password")

        _remote_api = PiholeApiClient(url, password)
        _remote_url = url
        return _remote_api

    def has_remote_pi(self) -> bool:
        """Check if a remote Pi-hole is configured."""
        config = self.get_config()
        return bool(config.remote_pihole_url)

    # ── Failover Logic ────────────────────────────────────────────────

    async def check_health_and_failover(self) -> None:
        """Check remote Pi-hole health and trigger failover/failback if needed.

        Called periodically by the background health check loop.
        """
        global _fail_count

        config = self.get_config()
        if not config.remote_pihole_url:
            return  # No remote Pi → nothing to do

        remote_api = self._get_remote_api()
        if remote_api is None:
            return

        remote_ok = await remote_api.is_connected()

        if remote_ok and config.failover_active:
            # Pi is back online → failback: set NAS upstream to Pi IP
            await self._switch_upstream(config.remote_pihole_url)
            config.failover_active = False
            config.last_failover_at = datetime.now(timezone.utc)
            self._db.commit()
            _fail_count = 0
            logger.info("Pi-hole failback: Primary (Pi) restored, upstream → %s", config.remote_pihole_url)

        elif not remote_ok and not config.failover_active:
            _fail_count += 1
            if _fail_count >= _FAIL_THRESHOLD:
                # Pi offline → failover: set NAS upstream to public DNS
                await self._switch_upstream("1.1.1.1;1.0.0.1")
                config.failover_active = True
                config.last_failover_at = datetime.now(timezone.utc)
                self._db.commit()
                _fail_count = 0
                logger.warning("Pi-hole failover: Primary (Pi) unreachable, NAS filtering with upstream 1.1.1.1;1.0.0.1")

        elif remote_ok:
            _fail_count = 0

    async def _switch_upstream(self, dns: str) -> None:
        """Change the NAS Pi-hole upstream DNS and restart DNS resolver.

        Args:
            dns: Semicolon-separated upstream DNS servers, or a Pi-hole URL
                 like http://192.168.1.50:80 from which the IP is extracted.
        """
        # Extract IP from URL if needed (e.g. "http://192.168.1.50:80" → "192.168.1.50")
        upstreams: list[str] = []
        for entry in dns.split(";"):
            entry = entry.strip()
            if entry.startswith("http://") or entry.startswith("https://"):
                from urllib.parse import urlparse
                parsed = urlparse(entry)
                upstreams.append(parsed.hostname or entry)
            else:
                upstreams.append(entry)

        # Use the local backend's API to change upstream DNS
        backend = self._get_backend()
        if hasattr(backend, "_api"):
            try:
                await backend._api.put(
                    "/api/config",
                    json={"config": {"dns": {"upstreams": upstreams}}},
                )
                await backend._api.post("/api/action/restartdns")
                logger.info("NAS Pi-hole upstream switched to %s", upstreams)
            except Exception as exc:
                logger.error("Failed to switch NAS Pi-hole upstream: %s", exc)
        else:
            logger.debug("Backend has no _api attribute — upstream switch skipped (dev mode)")

    async def get_failover_status(self) -> dict[str, Any]:
        """Return the current failover status for the API."""
        config = self.get_config()
        remote_configured = bool(config.remote_pihole_url)
        remote_connected = False

        if remote_configured:
            remote_api = self._get_remote_api()
            if remote_api is not None:
                try:
                    remote_connected = await remote_api.is_connected()
                except Exception:
                    remote_connected = False

        # Determine active source
        if not remote_configured:
            active_source = "local"
        elif config.failover_active:
            active_source = "local"
        else:
            active_source = "remote"

        return {
            "remote_configured": remote_configured,
            "remote_connected": remote_connected,
            "failover_active": config.failover_active,
            "active_source": active_source,
            "remote_url": config.remote_pihole_url,
            "last_failover_at": config.last_failover_at,
        }

    # ── Delegation Methods ────────────────────────────────────────────
    # When a remote Pi is configured and online, stats come from it.
    # Otherwise, the local NAS backend is used.

    def _get_active_backend(self) -> Any:
        """Get the backend that should serve stats/queries.

        If remote Pi is configured and not in failover → use remote (via RemotePiholeBackend).
        Otherwise → use local backend.
        """
        config = self.get_config()

        # In dev mode, always use dev backend
        if settings.is_dev_mode or getattr(settings, "pihole_force_dev_backend", False):
            return self._get_backend()

        # If remote is configured and not in failover, create a remote backend for stats
        if config.remote_pihole_url and not config.failover_active:
            remote_api = self._get_remote_api()
            if remote_api is not None:
                from app.services.pihole.remote_backend import RemotePiholeBackend
                # Create a lightweight wrapper using the cached API client
                # We don't cache this as a full backend to avoid lifecycle issues
                password = ""
                if config.remote_password_encrypted:
                    try:
                        password = VPNEncryption.decrypt_key(config.remote_password_encrypted)
                    except Exception:
                        pass
                return RemotePiholeBackend(config.remote_pihole_url, password)

        return self._get_backend()

    async def _safe_call(self, coro: Awaitable[dict[str, Any]]) -> dict[str, Any]:
        """Execute a backend coroutine, catching connection errors.

        Wraps all delegation calls so that unreachable Docker/remote Pi-hole
        instances return a clean 503 instead of an unhandled 500.
        """
        try:
            return await coro
        except httpx.ConnectError as exc:
            logger.warning("Pi-hole backend unreachable (connect): %s", exc)
            raise HTTPException(status_code=503, detail="Pi-hole is unreachable (connection refused)")
        except ValueError as exc:
            logger.warning("Pi-hole authentication failed: %s", exc)
            raise HTTPException(status_code=503, detail="Pi-hole authentication failed")
        except httpx.HTTPStatusError as exc:
            logger.warning("Pi-hole rejected request (HTTP %s): %s", exc.response.status_code, exc)
            raise HTTPException(status_code=503, detail=f"Pi-hole rejected the request (HTTP {exc.response.status_code})")
        except httpx.HTTPError as exc:
            logger.warning("Pi-hole communication error: %s", exc)
            raise HTTPException(status_code=503, detail="Pi-hole communication error")
        except (ConnectionError, OSError, RuntimeError) as exc:
            logger.warning("Pi-hole backend unreachable: %s", exc)
            raise HTTPException(status_code=503, detail="Pi-hole is unreachable")

    async def get_status(self) -> dict[str, Any]:
        try:
            result = await self._get_active_backend().get_status()
        except (httpx.ConnectError, httpx.HTTPError, ConnectionError, OSError, RuntimeError, ValueError) as exc:
            logger.warning("Pi-hole backend unreachable (status): %s", exc)
            config = self.get_config()
            result = {
                "mode": config.mode,
                "connected": False,
                "blocking_enabled": False,
                "version": None,
                "container_running": None,
                "container_status": "unreachable",
                "uptime": None,
            }
        # Augment with failover info
        config = self.get_config()
        if config.remote_pihole_url:
            result["failover_active"] = config.failover_active
            result["active_source"] = "local" if config.failover_active else "remote"
        return result

    async def get_summary(self) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().get_summary())

    async def get_blocking(self) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().get_blocking())

    async def set_blocking(self, enabled: bool, timer: int | None = None) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().set_blocking(enabled, timer))

    async def get_queries(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().get_queries(limit, offset))

    async def get_top_domains(self, count: int = 10) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().get_top_domains(count))

    async def get_top_blocked(self, count: int = 10) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().get_top_blocked(count))

    async def get_top_clients(self, count: int = 10) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().get_top_clients(count))

    async def get_history(self) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().get_history())

    async def get_domains(self, list_type: str, kind: str) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().get_domains(list_type, kind))

    async def add_domain(self, list_type: str, kind: str, domain: str, comment: str = "") -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().add_domain(list_type, kind, domain, comment))

    async def remove_domain(self, list_type: str, kind: str, domain: str) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().remove_domain(list_type, kind, domain))

    async def get_adlists(self) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().get_adlists())

    async def add_adlist(self, url: str, comment: str = "") -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().add_adlist(url, comment))

    async def remove_adlist(self, address: str) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().remove_adlist(address))

    async def toggle_adlist(self, address: str, enabled: bool) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().toggle_adlist(address, enabled))

    async def update_gravity(self) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().update_gravity())

    async def get_local_dns(self) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().get_local_dns())

    async def add_local_dns(self, domain: str, ip: str) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().add_local_dns(domain, ip))

    async def remove_local_dns(self, domain: str, ip: str) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().remove_local_dns(domain, ip))

    async def restart_dns(self) -> dict[str, Any]:
        return await self._safe_call(self._get_active_backend().restart_dns())

    # Container operations always use the local backend (NAS Docker)
    async def deploy_container(self, config: dict[str, Any]) -> dict[str, Any]:
        # Merge DNS settings from DB config into deploy config
        db_config = self.get_config()
        config["dns_settings"] = {
            "dnssec": db_config.dns_dnssec,
            "rev_server": db_config.dns_rev_server,
            "rate_limit_count": db_config.dns_rate_limit_count,
            "rate_limit_interval": db_config.dns_rate_limit_interval,
            "domain_needed": db_config.dns_domain_needed,
            "bogus_priv": db_config.dns_bogus_priv,
            "domain_name": db_config.dns_domain_name,
            "expand_hosts": db_config.dns_expand_hosts,
        }

        # Keep a reference to the deploying backend — it has the correct API
        # client with the new password for wait_for_ready polling.
        deploying_backend = self.backend
        result = await self._safe_call(deploying_backend.deploy_container(config))

        # 1. Persist password IMMEDIATELY (before waiting) so other workers
        #    read the correct password from DB during the 13-60s wait window.
        if result.get("success") and result.get("password"):
            try:
                db_config = self.get_config()
                db_config.password_encrypted = VPNEncryption.encrypt_key(
                    result["password"]
                )
                self._db.commit()
            except Exception as exc:
                logger.warning("Failed to persist deploy password: %s", exc)

        # 2. Reset backend singleton so next call reconnects with fresh config
        global _backend, _backend_mode
        _backend = None
        _backend_mode = None

        # 3. Signal all workers NOW — they'll get the correct password from DB
        write_shm(PIHOLE_DEPLOY_TS_FILE, {"ts": time.time()})

        # 4. Clean stale SHM SID files from the old container
        from pathlib import Path
        for f in Path(SHM_DIR).glob("pihole_sid_*.json"):
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass

        # 5. THEN wait for Pi-hole to become responsive (13-60s) using the
        #    deploying backend's API client which already has the new password.
        if result.get("success") and hasattr(deploying_backend, "wait_for_ready"):
            try:
                await deploying_backend.wait_for_ready()
            except Exception as exc:
                logger.warning("Pi-hole wait_for_ready failed: %s", exc)

        # 6. Run one-time init (populate /etc/pihole/versions etc.)
        if result.get("success") and hasattr(deploying_backend, "post_deploy_init"):
            try:
                await deploying_backend.post_deploy_init()
            except Exception as exc:
                logger.warning("post_deploy_init failed: %s", exc)

        return result

    async def start_container(self) -> dict[str, Any]:
        return await self._safe_call(self.backend.start_container())

    async def stop_container(self) -> dict[str, Any]:
        return await self._safe_call(self.backend.stop_container())

    async def remove_container(self) -> dict[str, Any]:
        return await self._safe_call(self.backend.remove_container())

    async def update_container(self) -> dict[str, Any]:
        return await self._safe_call(self.backend.update_container())

    async def get_container_logs(self, lines: int = 100) -> dict[str, Any]:
        return await self._safe_call(self.backend.get_container_logs(lines))

    # ── VPN DNS Helper ────────────────────────────────────────────────

    def get_vpn_dns(self) -> str:
        """Return the DNS server to use for VPN clients.

        Returns Pi-hole VPN IP (10.8.0.1) if active and configured, else fallback.
        """
        config = self.get_config()
        if config.mode != "disabled" and config.use_as_vpn_dns:
            return "10.8.0.1"
        return "1.1.1.1"

    # ── Service Status ────────────────────────────────────────────────

    def get_service_status(self) -> dict[str, Any]:
        """Return service status for the service registry."""
        config = self.get_config()
        return {
            "is_running": config.mode != "disabled",
            "mode": config.mode,
            "use_as_vpn_dns": config.use_as_vpn_dns,
            "failover_active": config.failover_active,
            "remote_configured": bool(config.remote_pihole_url),
        }

    # ── Local DNS Auto-Registration ──────────────────────────────────

    async def ensure_local_dns_records(self) -> None:
        """Register .local DNS records in Pi-hole for LAN access.

        Ensures that baluhost.local and baluhole.local resolve to the NAS IP.
        Idempotent — skips records that already exist with the correct IP.
        Errors are logged but not propagated (Pi-hole may not be ready yet).
        """
        config = self.get_config()
        if config.mode == "disabled":
            return

        # Determine NAS LAN IP (same method as NetworkDiscoveryService)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            nas_ip = s.getsockname()[0]
            s.close()
        except Exception as exc:
            logger.warning("Cannot determine local IP for DNS registration: %s", exc)
            return

        # Records to ensure
        required_records = {
            f"{settings.mdns_hostname}.local": nas_ip,
            "baluhole.local": nas_ip,
        }

        try:
            backend = self._get_backend()
            if not hasattr(backend, "_api"):
                logger.debug("Pi-hole backend has no API client — DNS registration skipped (dev mode)")
                return

            api = backend._api

            # Fetch existing local DNS records
            existing_data = await api.get_local_dns()
            # Pi-hole v6 returns {"config": {"dns": {"hosts": [...]}}}
            hosts_raw = existing_data
            if "config" in hosts_raw:
                hosts_raw = hosts_raw["config"]
            if "dns" in hosts_raw:
                hosts_raw = hosts_raw["dns"]
            hosts_list = hosts_raw.get("hosts", [])

            # Build lookup: hostname → ip from existing records
            # Each entry is "ip hostname" string
            existing: dict[str, str] = {}
            for entry in hosts_list:
                if isinstance(entry, str):
                    parts = entry.split(None, 1)
                    if len(parts) == 2:
                        existing[parts[1]] = parts[0]

            # Create or update records
            registered = []
            for hostname, ip in required_records.items():
                if existing.get(hostname) == ip:
                    continue  # Already correct
                if hostname in existing:
                    # IP changed — remove old record first
                    await api.remove_local_dns(hostname, existing[hostname])
                await api.add_local_dns(hostname, ip)
                registered.append(hostname)

            if registered:
                logger.info("Registered local DNS records in Pi-hole: %s → %s", registered, nas_ip)
            else:
                logger.debug("Local DNS records already up-to-date in Pi-hole")

        except Exception as exc:
            logger.warning("Failed to register local DNS records in Pi-hole: %s", exc)


async def _safe_close(backend: Any) -> None:
    """Safely close a backend, ignoring errors."""
    if hasattr(backend, "close"):
        try:
            await backend.close()
        except Exception:
            pass


def get_pihole_service(db: Session) -> PiholeService:
    """Factory for PiholeService instances."""
    return PiholeService(db)
