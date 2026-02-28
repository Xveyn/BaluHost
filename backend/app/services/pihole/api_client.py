"""Pi-hole v6 REST API client using httpx."""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional
from urllib.parse import quote

import httpx

from app.services.monitoring.shm import SHM_DIR, read_shm, write_shm

logger = logging.getLogger(__name__)


class PiholeApiClient:
    """HTTP client for the Pi-hole v6 API.

    Handles authentication via session ID (SID) and automatic re-auth on 401.
    """

    def __init__(self, base_url: str, password: str, timeout: float = 10.0) -> None:
        """Initialize the Pi-hole API client.

        Args:
            base_url: Pi-hole base URL (e.g. http://localhost:8053)
            password: Pi-hole web interface password
            timeout: Request timeout in seconds
        """
        self._base_url = base_url.rstrip("/")
        self._password = password
        self._timeout = timeout
        self._sid: Optional[str] = None
        self._csrf: Optional[str] = None
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_connections=5,
                max_keepalive_connections=2,
                keepalive_expiry=30.0,
            ),
        )

    def _sid_filename(self) -> str:
        """SHM filename for sharing SID across workers, keyed by base URL."""
        url_hash = hashlib.md5(self._base_url.encode()).hexdigest()[:8]
        return f"pihole_sid_{url_hash}.json"

    async def close(self) -> None:
        """Logout the session and close the underlying HTTP client."""
        if self._sid:
            await self._logout(self._sid)
        await self._client.aclose()

    # ── Authentication ────────────────────────────────────────────────

    async def _authenticate(self) -> None:
        """Authenticate with Pi-hole and obtain a session ID."""
        try:
            resp = await self._client.post(
                f"{self._base_url}/api/auth",
                json={"password": self._password},
            )
            if resp.status_code == 401:
                body = resp.text
                logger.error("Pi-hole auth returned 401 (session limit or not ready): %s", body[:200])
                raise httpx.HTTPStatusError(
                    f"Pi-hole auth rejected (401): {body[:100]}",
                    request=resp.request, response=resp,
                )
            resp.raise_for_status()
            data = resp.json()
            session = data.get("session", {})

            # Pi-hole v6 returns 200 with valid=false for wrong passwords
            if not session.get("valid", False):
                logger.error("Pi-hole auth rejected (valid=false)")
                raise ValueError("Pi-hole authentication failed: invalid credentials")

            self._sid = session.get("sid")
            self._csrf = session.get("csrf")
            if not self._sid:
                logger.error("Pi-hole auth response missing SID: %s", data)
                raise ValueError("Pi-hole authentication failed: no SID returned")

            # Share SID + CSRF with other workers via SHM
            write_shm(self._sid_filename(), {"sid": self._sid, "csrf": self._csrf, "base_url": self._base_url})
            logger.debug("Pi-hole authenticated, SID obtained and shared via SHM")
        except httpx.HTTPError as exc:
            logger.error("Pi-hole authentication failed: %s: %s", type(exc).__name__, exc)
            raise

    async def _logout(self, sid: str) -> None:
        """Logout a Pi-hole session to free the API seat. Best-effort."""
        try:
            resp = await self._client.delete(
                f"{self._base_url}/api/auth",
                headers={"X-FTL-SID": sid},
            )
            _ = resp.text  # Consume body to prevent connection reuse corruption
            logger.debug("Pi-hole logout: status=%s", resp.status_code)
        except Exception as exc:
            logger.debug("Pi-hole logout failed (best-effort): %s", exc)

    def _auth_headers(self) -> dict[str, str]:
        """Return authorization headers with current SID and CSRF token."""
        headers: dict[str, str] = {}
        if self._sid:
            headers["X-FTL-SID"] = self._sid
        if self._csrf:
            headers["X-FTL-CSRF"] = self._csrf
        return headers

    async def _ensure_auth(self) -> None:
        """Ensure we have a valid session, authenticate if needed.

        Tries to reuse a shared SID from SHM before authenticating fresh.
        """
        if self._sid:
            return

        # Try to pick up a SID shared by another worker
        shared = read_shm(self._sid_filename(), max_age_seconds=300)
        if shared and shared.get("sid") and shared.get("base_url") == self._base_url:
            self._sid = shared["sid"]
            self._csrf = shared.get("csrf")
            logger.debug("Pi-hole SID loaded from shared cache")
            return

        await self._authenticate()

    # ── Generic Request ───────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        json: Any = None,
        params: dict[str, Any] | None = None,
        retry_auth: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to the Pi-hole API.

        Automatically retries once with fresh auth on 401.
        """
        await self._ensure_auth()

        url = f"{self._base_url}{path}"
        try:
            resp = await self._client.request(
                method,
                url,
                headers=self._auth_headers(),
                json=json,
                params=params,
                timeout=timeout or self._timeout,
            )

            # Re-authenticate on 401 and retry once
            if resp.status_code == 401 and retry_auth:
                _ = resp.text  # Consume body before connection returns to pool
                stale_sid = self._sid
                logger.debug("Pi-hole returned 401, checking SHM for refreshed SID...")

                # Check if another worker already refreshed the SID
                shared = read_shm(self._sid_filename(), max_age_seconds=300)
                if shared and shared.get("sid") and shared["sid"] != stale_sid and shared.get("base_url") == self._base_url:
                    self._sid = shared["sid"]
                    self._csrf = shared.get("csrf")
                    logger.debug("Pi-hole SID refreshed from SHM (another worker)")
                else:
                    # Logout old session to free the seat, then authenticate fresh
                    if stale_sid:
                        await self._logout(stale_sid)
                    self._sid = None
                    self._csrf = None
                    await self._authenticate()

                return await self._request(method, path, json=json, params=params, retry_auth=False, timeout=timeout)

            resp.raise_for_status()

            # 204 No Content or empty body
            if resp.status_code == 204 or not resp.content:
                return {}

            # Some Pi-hole endpoints return plain text (e.g. action/gravity)
            content_type = resp.headers.get("content-type", "")
            if "application/json" not in content_type:
                return {}

            return resp.json()

        except (httpx.HTTPError, ValueError) as exc:
            logger.error("Pi-hole API request failed: %s %s → %s: %s", method, path, type(exc).__name__, exc)
            raise

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET request."""
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: Any = None) -> dict[str, Any]:
        """POST request."""
        return await self._request("POST", path, json=json)

    async def put(self, path: str, json: Any = None) -> dict[str, Any]:
        """PUT request."""
        return await self._request("PUT", path, json=json)

    async def delete(self, path: str, json: Any = None) -> dict[str, Any]:
        """DELETE request."""
        return await self._request("DELETE", path, json=json)

    # ── Convenience Methods ───────────────────────────────────────────

    async def is_connected(self) -> bool:
        """Check if Pi-hole API is reachable and authenticated."""
        try:
            await self._ensure_auth()
            resp = await self._client.get(
                f"{self._base_url}/api/info/version",
                headers=self._auth_headers(),
            )
            _ = resp.text  # Consume body to prevent connection reuse corruption
            return resp.status_code == 200
        except Exception:
            return False

    async def get_version(self) -> str | None:
        """Get Pi-hole FTL version string."""
        try:
            data = await self.get("/api/info/version")
            # Pi-hole v6 may wrap everything in {"version": {...}}
            version = data.get("version")
            if isinstance(version, str):
                return version
            # Unwrap the envelope so ftl/core parsing below works
            if isinstance(version, dict):
                data = version
            # Try extracting from nested structure
            ftl = data.get("ftl", {})
            if isinstance(ftl, dict):
                local = ftl.get("local", {})
                if isinstance(local, dict) and "version" in local:
                    return local["version"]
                if "version" in ftl:
                    return ftl["version"]
            core = data.get("core", {})
            if isinstance(core, dict):
                local = core.get("local", {})
                if isinstance(local, dict) and "version" in local:
                    return local["version"]
            return None
        except Exception:
            return None

    # ── Pi-hole API Endpoints ─────────────────────────────────────────

    async def get_summary(self) -> dict[str, Any]:
        """GET /api/stats/summary"""
        return await self.get("/api/stats/summary")

    async def get_blocking(self) -> dict[str, Any]:
        """GET /api/dns/blocking"""
        return await self.get("/api/dns/blocking")

    async def set_blocking(self, enabled: bool, timer: int | None = None) -> dict[str, Any]:
        """POST /api/dns/blocking"""
        payload: dict[str, Any] = {"blocking": enabled}
        if timer is not None and not enabled:
            payload["timer"] = timer
        return await self.post("/api/dns/blocking", json=payload)

    async def get_queries(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """GET /api/queries"""
        params: dict[str, Any] = {"length": limit}
        if offset:
            params["start"] = offset
        return await self.get("/api/queries", params=params)

    async def get_top_domains(self, count: int = 10) -> dict[str, Any]:
        """GET /api/stats/top_domains"""
        return await self.get("/api/stats/top_domains", params={"count": count})

    async def get_top_blocked(self, count: int = 10) -> dict[str, Any]:
        """GET /api/stats/top_domains?blocked=true"""
        return await self.get("/api/stats/top_domains", params={"count": count, "blocked": "true"})

    async def get_top_clients(self, count: int = 10) -> dict[str, Any]:
        """GET /api/stats/top_clients"""
        return await self.get("/api/stats/top_clients", params={"count": count})

    async def get_history(self) -> dict[str, Any]:
        """GET /api/history"""
        return await self.get("/api/history")

    async def get_domains(self, list_type: str, kind: str) -> dict[str, Any]:
        """GET /api/domains/{type}/{kind}"""
        return await self.get(f"/api/domains/{list_type}/{kind}")

    async def add_domain(self, list_type: str, kind: str, domain: str, comment: str = "") -> dict[str, Any]:
        """POST /api/domains/{type}/{kind} — add a domain to allow/deny list."""
        payload: dict[str, Any] = {"domain": domain}
        if comment:
            payload["comment"] = comment
        return await self.post(f"/api/domains/{list_type}/{kind}", json=payload)

    async def remove_domain(self, list_type: str, kind: str, domain: str) -> dict[str, Any]:
        """DELETE /api/domains/{type}/{kind}/{domain} — domain encoded in URL."""
        encoded = quote(domain, safe="")
        return await self.delete(f"/api/domains/{list_type}/{kind}/{encoded}")

    async def get_adlists(self) -> dict[str, Any]:
        """GET /api/lists"""
        return await self.get("/api/lists")

    async def add_adlist(self, url: str, comment: str = "") -> dict[str, Any]:
        """POST /api/lists"""
        payload: dict[str, Any] = {"address": url}
        if comment:
            payload["comment"] = comment
        return await self.post("/api/lists", json=payload)

    async def remove_adlist(self, address: str) -> dict[str, Any]:
        """DELETE /api/lists/{address} — address URL-encoded in path."""
        encoded = quote(address, safe="")
        return await self.delete(f"/api/lists/{encoded}")

    async def update_adlist(self, address: str, enabled: bool) -> dict[str, Any]:
        """PUT /api/lists/{address} — toggle adlist enabled state."""
        encoded = quote(address, safe="")
        return await self.put(f"/api/lists/{encoded}", json={"enabled": enabled})

    async def update_gravity(self) -> dict[str, Any]:
        """POST /api/action/gravity — returns plain text, not JSON."""
        await self._ensure_auth()
        url = f"{self._base_url}/api/action/gravity"
        headers = self._auth_headers()
        headers["Connection"] = "close"  # Prevent connection reuse corruption
        resp = await self._client.request(
            "POST", url,
            headers=headers,
            timeout=120.0,
        )
        resp.raise_for_status()
        _ = resp.text  # Consume body
        return {"success": True}

    async def get_local_dns(self) -> dict[str, Any]:
        """GET /api/config/dns/hosts"""
        return await self.get("/api/config/dns/hosts")

    async def add_local_dns(self, domain: str, ip: str) -> dict[str, Any]:
        """PUT /api/config/dns/hosts/{ip hostname} — value URL-encoded in path, no body."""
        value = f"{ip} {domain}"
        encoded = quote(value, safe="")
        return await self.put(f"/api/config/dns/hosts/{encoded}")

    async def remove_local_dns(self, domain: str, ip: str) -> dict[str, Any]:
        """DELETE /api/config/dns/hosts/{ip hostname} — value URL-encoded in path."""
        value = f"{ip} {domain}"
        encoded = quote(value, safe="")
        return await self.delete(f"/api/config/dns/hosts/{encoded}")

    async def restart_dns(self) -> dict[str, Any]:
        """POST /api/action/restartdns"""
        return await self.post("/api/action/restartdns")

    async def set_ftl_config(self, section: str, key: str, value: Any) -> dict[str, Any]:
        """PATCH /api/config — set a single FTL config value (Pi-hole v6 format)."""
        return await self._request("PATCH", "/api/config", json={"config": {section: {key: value}}})

    async def get_ftl_config(self, key: str = "") -> dict[str, Any]:
        """GET /api/config/{key} — read FTL configuration."""
        path = f"/api/config/{key}" if key else "/api/config"
        return await self.get(path)
