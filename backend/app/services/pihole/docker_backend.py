"""Docker-based Pi-hole backend using the Docker SDK (docker-py)."""

from __future__ import annotations

import asyncio
import logging
import secrets
from functools import partial
from typing import Any, Optional

from app.services.pihole.api_client import PiholeApiClient

logger = logging.getLogger(__name__)

# Container configuration defaults
CONTAINER_NAME = "baluhost-pihole"
IMAGE_NAME = "pihole/pihole"
DEFAULT_TAG = "latest"
DNS_PORT = 53
DEFAULT_WEB_PORT = 8053


class ContainerManager:
    """Manages the Pi-hole Docker container lifecycle via docker-py.

    Uses the Docker Engine API through the Unix socket — no shell=True needed.
    """

    def __init__(self) -> None:
        self._client: Any = None  # docker.DockerClient (lazy import)

    def _get_client(self) -> Any:
        """Lazy-initialize Docker client."""
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
            except ImportError:
                raise RuntimeError(
                    "docker package not installed. Install with: pip install docker>=7.0.0"
                )
            except Exception as exc:
                raise RuntimeError(f"Cannot connect to Docker daemon: {exc}")
        return self._client

    def _get_container(self) -> Any:
        """Get the Pi-hole container if it exists."""
        try:
            client = self._get_client()
            return client.containers.get(CONTAINER_NAME)
        except Exception:
            return None

    async def _run_sync(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous Docker SDK call in a thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(fn, *args, **kwargs))

    async def get_status(self) -> dict[str, Any]:
        """Get container status."""
        try:
            container = await self._run_sync(self._get_container)
            if container is None:
                return {"exists": False, "running": False, "status": "not_found"}
            attrs = container.attrs or {}
            state = attrs.get("State", {})
            return {
                "exists": True,
                "running": state.get("Running", False),
                "status": state.get("Status", "unknown"),
                "started_at": state.get("StartedAt"),
                "image": attrs.get("Config", {}).get("Image", ""),
            }
        except Exception as exc:
            logger.warning("Failed to get container status: %s", exc)
            return {"exists": False, "running": False, "status": "error", "error": str(exc)}

    async def deploy(
        self,
        image_tag: str = DEFAULT_TAG,
        web_port: int = DEFAULT_WEB_PORT,
        upstream_dns: str = "1.1.1.1;1.0.0.1",
        timezone: str = "Europe/Berlin",
        password: str = "",
        dns_settings: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Pull image and create/start the container."""
        client = self._get_client()

        # Generate a password if none provided
        if not password:
            password = secrets.token_urlsafe(16)

        full_image = f"{IMAGE_NAME}:{image_tag}"

        # Pull image
        logger.info("Pulling Docker image %s...", full_image)
        await self._run_sync(client.images.pull, IMAGE_NAME, tag=image_tag)

        # Remove existing container if present
        existing = await self._run_sync(self._get_container)
        if existing:
            logger.info("Removing existing container %s", CONTAINER_NAME)
            await self._run_sync(existing.remove, force=True)

        # Remove config volume so password env var takes effect on fresh boot
        try:
            vol = await self._run_sync(client.volumes.get, "pihole_config")
            await self._run_sync(vol.remove)
            logger.info("Removed Docker volume pihole_config for clean deploy")
        except Exception:
            pass  # Volume doesn't exist yet — first deploy

        # Create and start container
        env = {
            "TZ": timezone,
            "FTLCONF_webserver_api_password": password,
            "FTLCONF_dns_listeningMode": "ALL",
            "FTLCONF_dns_upstreams": upstream_dns,
            "FTLCONF_webserver_port": str(web_port),
            # Force IPv4-only for FTL resolver — prevents gravity "Connection
            # Refused" when FTL's embedded libcurl tries IPv6 first inside the
            # container (pi-hole/docker-pi-hole#1885).
            "FTLCONF_resolver_resolveIPv6": "false",
        }

        # DNS settings from saved config (FTLCONF_* env vars, read-only in Pi-hole v6 UI)
        if dns_settings:
            if dns_settings.get("dnssec"):
                env["FTLCONF_dns_dnssec"] = "true"
            if dns_settings.get("rev_server"):
                env["FTLCONF_dns_revServers"] = dns_settings["rev_server"]
            if dns_settings.get("rate_limit_count") is not None:
                env["FTLCONF_dns_rateLimit_count"] = str(dns_settings["rate_limit_count"])
            if dns_settings.get("rate_limit_interval") is not None:
                env["FTLCONF_dns_rateLimit_interval"] = str(dns_settings["rate_limit_interval"])
            if dns_settings.get("domain_needed"):
                env["FTLCONF_dns_domainNeeded"] = "true"
            if not dns_settings.get("bogus_priv", True):
                env["FTLCONF_dns_bogusPriv"] = "false"
            if dns_settings.get("domain_name") and dns_settings["domain_name"] != "lan":
                env["FTLCONF_dns_domain"] = dns_settings["domain_name"]
            if dns_settings.get("expand_hosts"):
                env["FTLCONF_dns_expandHosts"] = "true"

        volumes = {"pihole_config": {"bind": "/etc/pihole", "mode": "rw"}}

        # Host networking: container shares the host network stack directly.
        # This avoids Docker bridge DNS proxy issues that prevent Pi-hole from
        # downloading blocklists (pi-hole/docker-pi-hole#1885).
        # No port mapping needed — Pi-hole binds directly to host ports.
        logger.info("Creating container %s from %s", CONTAINER_NAME, full_image)
        container = await self._run_sync(
            client.containers.run,
            full_image,
            name=CONTAINER_NAME,
            detach=True,
            environment=env,
            network_mode="host",
            volumes=volumes,
            cap_add=["NET_ADMIN", "SYS_NICE"],
            restart_policy={"Name": "unless-stopped"},
        )

        # Fix container DNS — Docker may override /etc/resolv.conf even in host mode
        try:
            dns_entries = [ip.strip() for ip in upstream_dns.split(";") if ip.strip()]
            resolv_lines = "\\n".join(f"nameserver {ip}" for ip in dns_entries)
            await self._run_sync(
                container.exec_run,
                ["sh", "-c", f"printf '{resolv_lines}\\n' > /etc/resolv.conf"],
            )
            logger.info("Wrote /etc/resolv.conf into container: %s", dns_entries)
        except Exception as exc:
            logger.warning("Could not fix container resolv.conf: %s", exc)

        return {
            "success": True,
            "message": f"Container {CONTAINER_NAME} deployed",
            "container_status": "running",
            "password": password,
        }

    async def start(self) -> dict[str, Any]:
        """Start an existing container."""
        container = await self._run_sync(self._get_container)
        if container is None:
            return {"success": False, "message": "Container not found", "container_status": None}
        await self._run_sync(container.start)
        return {"success": True, "message": "Container started", "container_status": "running"}

    async def stop(self) -> dict[str, Any]:
        """Stop the container."""
        container = await self._run_sync(self._get_container)
        if container is None:
            return {"success": False, "message": "Container not found", "container_status": None}
        await self._run_sync(container.stop, timeout=30)
        return {"success": True, "message": "Container stopped", "container_status": "exited"}

    async def remove(self) -> dict[str, Any]:
        """Remove the container."""
        container = await self._run_sync(self._get_container)
        if container is None:
            return {"success": False, "message": "Container not found", "container_status": None}
        await self._run_sync(container.remove, force=True)
        return {"success": True, "message": "Container removed", "container_status": None}

    async def update(self, image_tag: str = DEFAULT_TAG, web_port: int = DEFAULT_WEB_PORT,
                     upstream_dns: str = "1.1.1.1;1.0.0.1", timezone: str = "Europe/Berlin",
                     password: str = "") -> dict[str, Any]:
        """Pull latest image and recreate the container."""
        return await self.deploy(
            image_tag=image_tag,
            web_port=web_port,
            upstream_dns=upstream_dns,
            timezone=timezone,
            password=password,
        )

    async def exec_command(self, command: list[str]) -> dict[str, Any]:
        """Execute a command inside the container."""
        container = await self._run_sync(self._get_container)
        if container is None:
            return {"exit_code": -1, "output": "Container not found"}
        result = await self._run_sync(container.exec_run, command)
        output = result.output.decode("utf-8", errors="replace") if isinstance(result.output, bytes) else str(result.output)
        return {"exit_code": result.exit_code, "output": output}

    async def get_logs(self, lines: int = 100) -> dict[str, Any]:
        """Get container logs."""
        container = await self._run_sync(self._get_container)
        if container is None:
            return {"logs": "", "lines": 0}
        raw_logs = await self._run_sync(container.logs, tail=lines, timestamps=True)
        log_str = raw_logs.decode("utf-8", errors="replace") if isinstance(raw_logs, bytes) else str(raw_logs)
        log_lines = log_str.strip().split("\n") if log_str.strip() else []
        return {"logs": log_str, "lines": len(log_lines)}


class LocalDockerPiholeBackend:
    """Pi-hole backend for a Docker container running on the NAS.

    Combines ContainerManager (lifecycle) with PiholeApiClient (Pi-hole API).
    """

    def __init__(self, pihole_url: str, password: str) -> None:
        self._container_mgr = ContainerManager()
        self._api = PiholeApiClient(pihole_url, password)
        self._pihole_url = pihole_url
        self._password = password

    async def close(self) -> None:
        """Clean up resources."""
        await self._api.close()

    # ── Status & Summary ──────────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        container_status = await self._container_mgr.get_status()
        connected = False
        version = None
        blocking_enabled = False

        if container_status.get("running"):
            connected = await self._api.is_connected()
            if connected:
                version = await self._api.get_version()
                try:
                    blocking_data = await self._api.get_blocking()
                    blocking_enabled = blocking_data.get("blocking") == "enabled"
                except Exception:
                    pass

        # Compute uptime from Docker's StartedAt timestamp
        uptime = None
        started_at = container_status.get("started_at")
        if started_at and container_status.get("running"):
            try:
                from datetime import datetime, timezone
                # Docker returns ISO 8601 with nanoseconds; trim to microseconds
                started_str = started_at[:26].rstrip("Z") + "+00:00"
                started_dt = datetime.fromisoformat(started_str)
                uptime = int((datetime.now(timezone.utc) - started_dt).total_seconds())
            except Exception:
                pass

        return {
            "mode": "docker",
            "connected": connected,
            "blocking_enabled": blocking_enabled,
            "version": version,
            "container_running": container_status.get("running", False),
            "container_status": container_status.get("status", "unknown"),
            "uptime": uptime,
        }

    async def get_summary(self) -> dict[str, Any]:
        data = await self._api.get_summary()
        # Normalize Pi-hole v6 response fields
        queries = data.get("queries", {})
        return {
            "total_queries": queries.get("total", 0),
            "blocked_queries": queries.get("blocked", 0),
            "percent_blocked": queries.get("percent_blocked", 0),
            "unique_domains": data.get("unique_domains", 0),
            "forwarded_queries": queries.get("forwarded", 0),
            "cached_queries": queries.get("cached", 0),
            "clients_seen": data.get("clients", {}).get("total", 0),
            "gravity_size": data.get("gravity", {}).get("domains_being_blocked", 0),
            "gravity_last_updated": data.get("gravity", {}).get("last_update"),
        }

    # ── Blocking Control ──────────────────────────────────────────────

    async def get_blocking(self) -> dict[str, Any]:
        data = await self._api.get_blocking()
        return {
            "blocking": data.get("blocking", "unknown"),
            "timer": data.get("timer"),
        }

    async def set_blocking(self, enabled: bool, timer: int | None = None) -> dict[str, Any]:
        data = await self._api.set_blocking(enabled, timer)
        return {
            "blocking": data.get("blocking", "enabled" if enabled else "disabled"),
            "timer": data.get("timer"),
        }

    # ── Query Log ─────────────────────────────────────────────────────

    async def get_queries(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        data = await self._api.get_queries(limit, offset)
        queries = []
        for q in data.get("queries", []):
            queries.append({
                "timestamp": q.get("time", 0),
                "domain": q.get("domain", ""),
                "client": q.get("client", {}).get("ip", q.get("client", "")),
                "query_type": q.get("type", ""),
                "status": q.get("status", ""),
                "reply_type": q.get("reply", {}).get("type", ""),
                "response_time": q.get("reply", {}).get("time", 0),
            })
        return {"queries": queries, "total": data.get("recordsTotal", len(queries))}

    # ── Statistics ────────────────────────────────────────────────────

    async def get_top_domains(self, count: int = 10) -> dict[str, Any]:
        data = await self._api.get_top_domains(count)
        top = data.get("top_domains", data.get("domains", []))
        result = []
        if isinstance(top, dict):
            result = [{"domain": d, "count": c} for d, c in top.items()]
        elif isinstance(top, list):
            result = [{"domain": item.get("domain", ""), "count": item.get("count", 0)} for item in top]
        return {"top_permitted": result}

    async def get_top_blocked(self, count: int = 10) -> dict[str, Any]:
        data = await self._api.get_top_blocked(count)
        top = data.get("top_domains", data.get("domains", []))
        result = []
        if isinstance(top, dict):
            result = [{"domain": d, "count": c} for d, c in top.items()]
        elif isinstance(top, list):
            result = [{"domain": item.get("domain", ""), "count": item.get("count", 0)} for item in top]
        return {"top_blocked": result}

    async def get_top_clients(self, count: int = 10) -> dict[str, Any]:
        data = await self._api.get_top_clients(count)
        clients = data.get("top_clients", data.get("clients", []))
        result = []
        if isinstance(clients, dict):
            result = [{"client": ip, "name": None, "count": c} for ip, c in clients.items()]
        elif isinstance(clients, list):
            result = [
                {"client": item.get("ip", item.get("client", "")),
                 "name": item.get("name"),
                 "count": item.get("count", 0)}
                for item in clients
            ]
        return {"top_clients": result}

    async def get_history(self) -> dict[str, Any]:
        data = await self._api.get_history()
        history = []
        for entry in data.get("history", []):
            history.append({
                "timestamp": entry.get("timestamp", 0),
                "total": entry.get("total", 0),
                "blocked": entry.get("blocked", 0),
            })
        return {"history": history}

    # ── Domain Management ─────────────────────────────────────────────

    async def get_domains(self, list_type: str, kind: str) -> dict[str, Any]:
        data = await self._api.get_domains(list_type, kind)
        domains = []
        for d in data.get("domains", []):
            domains.append({
                "id": d.get("id"),
                "domain": d.get("domain", ""),
                "comment": d.get("comment", ""),
                "enabled": d.get("enabled", True),
                "date_added": d.get("date_added"),
                "date_modified": d.get("date_modified"),
            })
        return {"domains": domains}

    async def add_domain(self, list_type: str, kind: str, domain: str, comment: str = "") -> dict[str, Any]:
        return await self._api.add_domain(list_type, kind, domain, comment)

    async def remove_domain(self, list_type: str, kind: str, domain: str) -> dict[str, Any]:
        return await self._api.remove_domain(list_type, kind, domain)

    # ── Adlist Management ─────────────────────────────────────────────

    async def get_adlists(self) -> dict[str, Any]:
        data = await self._api.get_adlists()
        lists = []
        for item in data.get("lists", []):
            lists.append({
                "id": item.get("id"),
                "url": item.get("address", item.get("url", "")),
                "comment": item.get("comment", ""),
                "enabled": item.get("enabled", True),
                "number": item.get("number", 0),
                "date_added": item.get("date_added"),
                "date_modified": item.get("date_modified"),
            })
        return {"lists": lists}

    async def add_adlist(self, url: str, comment: str = "") -> dict[str, Any]:
        return await self._api.add_adlist(url, comment)

    async def remove_adlist(self, address: str) -> dict[str, Any]:
        return await self._api.remove_adlist(address)

    async def toggle_adlist(self, address: str, enabled: bool) -> dict[str, Any]:
        return await self._api.update_adlist(address, enabled)

    async def update_gravity(self) -> dict[str, Any]:
        # Fix container DNS if resolv.conf is broken (Docker override)
        try:
            result = await self._container_mgr.exec_command(
                ["sh", "-c", "printf 'nameserver 1.1.1.1\\nnameserver 1.0.0.1\\n' > /etc/resolv.conf"]
            )
            if result["exit_code"] == 0:
                logger.debug("Wrote fallback resolv.conf before gravity")
        except Exception:
            pass

        # Disable IPv6 resolution (prevents "Connection Refused" when FTL tries IPv6)
        try:
            await self._api.set_ftl_config("resolver", "resolveIPv6", False)
        except Exception as exc:
            logger.debug("Could not set resolveIPv6=false: %s", exc)

        return await self._api.update_gravity()

    # ── Local DNS ─────────────────────────────────────────────────────

    async def get_local_dns(self) -> dict[str, Any]:
        data = await self._api.get_local_dns()
        records = []
        hosts = data.get("config", {}).get("dns", {}).get("hosts", data.get("hosts", []))
        if isinstance(hosts, list):
            for entry in hosts:
                if isinstance(entry, str) and " " in entry:
                    parts = entry.split(None, 1)
                    records.append({"ip": parts[0], "domain": parts[1]})
                elif isinstance(entry, dict):
                    records.append({"domain": entry.get("host", entry.get("domain", "")), "ip": entry.get("ip", "")})
        return {"records": records}

    async def add_local_dns(self, domain: str, ip: str) -> dict[str, Any]:
        return await self._api.add_local_dns(domain, ip)

    async def remove_local_dns(self, domain: str, ip: str) -> dict[str, Any]:
        return await self._api.remove_local_dns(domain, ip)

    # ── Actions ───────────────────────────────────────────────────────

    async def restart_dns(self) -> dict[str, Any]:
        return await self._api.restart_dns()

    # ── Container Lifecycle ───────────────────────────────────────────

    async def deploy_container(self, config: dict[str, Any]) -> dict[str, Any]:
        web_port = config.get("web_port", DEFAULT_WEB_PORT)
        result = await self._container_mgr.deploy(
            image_tag=config.get("image_tag", DEFAULT_TAG),
            web_port=web_port,
            upstream_dns=config.get("upstream_dns", "1.1.1.1;1.0.0.1"),
            timezone=config.get("timezone", "Europe/Berlin"),
            password=config.get("password", ""),
            dns_settings=config.get("dns_settings"),
        )
        # Reinitialize API client with actual deploy port and new password
        if result.get("password"):
            new_password = result["password"]
            new_url = f"http://localhost:{web_port}"
            await self._api.close()
            self._api = PiholeApiClient(new_url, new_password)
            self._pihole_url = new_url

        # NOTE: Does NOT wait for ready here — caller handles ordering
        # (password must be persisted to DB before waiting, so other workers
        # can pick up the correct password during the 13-60s wait window)
        return result

    async def wait_for_ready(self, timeout: int = 60) -> None:
        """Wait for Pi-hole API to become responsive after deploy.

        Public wrapper so the service layer can call this AFTER persisting
        the password to DB and signalling other workers.
        """
        await self._wait_for_ready(timeout)

    async def _wait_for_ready(self, timeout: int = 60) -> None:
        """Wait for Pi-hole API to become responsive after deploy."""
        logger.info("Waiting for Pi-hole to start (up to %ds)...", timeout)
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                if await self._api.is_connected():
                    logger.info("Pi-hole is ready")
                    return
            except Exception:
                pass
            await asyncio.sleep(2)
        logger.warning("Pi-hole not ready after %ds — may still be starting", timeout)

    async def post_deploy_init(self) -> None:
        """Run one-time initialisation tasks inside the container."""
        container = await self._container_mgr._run_sync(self._container_mgr._get_container)
        if not container:
            return
        try:
            await self._container_mgr._run_sync(
                container.exec_run,
                ["pihole", "updatechecker"],
            )
            logger.info("Ran pihole updatechecker inside container")
        except Exception as exc:
            logger.warning("post_deploy_init: updatechecker failed: %s", exc)

    async def start_container(self) -> dict[str, Any]:
        return await self._container_mgr.start()

    async def stop_container(self) -> dict[str, Any]:
        return await self._container_mgr.stop()

    async def remove_container(self) -> dict[str, Any]:
        return await self._container_mgr.remove()

    async def update_container(self) -> dict[str, Any]:
        return await self._container_mgr.update(password=self._password)

    async def exec_diagnostic(self, command: list[str]) -> dict[str, Any]:
        """Execute a diagnostic command inside the container."""
        return await self._container_mgr.exec_command(command)

    async def get_container_logs(self, lines: int = 100) -> dict[str, Any]:
        return await self._container_mgr.get_logs(lines)
