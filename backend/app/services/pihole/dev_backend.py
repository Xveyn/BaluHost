"""Development mock backend for Pi-hole integration."""

from __future__ import annotations

import random
import time
from typing import Any


class DevPiholeBackend:
    """Mock Pi-hole backend for development and testing.

    Returns realistic-looking mock data without requiring Docker or a real Pi-hole instance.
    """

    def __init__(self) -> None:
        self._blocking_enabled = True
        self._blocking_timer: int | None = None
        self._domains: dict[str, list[dict]] = {
            "allow_exact": [
                {"id": 1, "domain": "example.com", "comment": "Test allow", "enabled": True},
            ],
            "allow_regex": [],
            "deny_exact": [
                {"id": 1, "domain": "ads.tracking.com", "comment": "Block tracker", "enabled": True},
                {"id": 2, "domain": "telemetry.evil.com", "comment": "", "enabled": True},
            ],
            "deny_regex": [
                {"id": 1, "domain": r"(.*)\.doubleclick\.net$", "comment": "Block doubleclick", "enabled": True},
            ],
        }
        self._adlists: list[dict] = [
            {"id": 1, "url": "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts", "comment": "StevenBlack unified", "enabled": True, "number": 85432},
            {"id": 2, "url": "https://adaway.org/hosts.txt", "comment": "AdAway default", "enabled": True, "number": 6789},
            {"id": 3, "url": "https://v.firebog.net/hosts/Easylist.txt", "comment": "Firebog Easylist", "enabled": True, "number": 14321},
        ]
        self._local_dns: list[dict] = [
            {"domain": "baluhost.local", "ip": "192.168.1.100"},
            {"domain": "nas.local", "ip": "192.168.1.100"},
        ]
        self._next_domain_id = 10
        self._next_adlist_id = 4
        self._start_time = time.time()

    # ── Status & Summary ──────────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        return {
            "mode": "dev",
            "connected": True,
            "blocking_enabled": self._blocking_enabled,
            "version": "Pi-hole v6.0 (mock)",
            "container_running": True,
            "container_status": "running",
            "uptime": int(time.time() - self._start_time),
        }

    async def get_summary(self) -> dict[str, Any]:
        total = random.randint(50000, 120000)
        blocked = int(total * random.uniform(0.15, 0.35))
        return {
            "total_queries": total,
            "blocked_queries": blocked,
            "percent_blocked": round(blocked / total * 100, 1) if total else 0,
            "unique_domains": random.randint(5000, 15000),
            "forwarded_queries": total - blocked - random.randint(1000, 5000),
            "cached_queries": random.randint(1000, 5000),
            "clients_seen": random.randint(5, 20),
            "gravity_size": sum(a.get("number", 0) for a in self._adlists),
            "gravity_last_updated": "2026-02-27T08:00:00Z",
        }

    # ── Blocking Control ──────────────────────────────────────────────

    async def get_blocking(self) -> dict[str, Any]:
        return {
            "blocking": "enabled" if self._blocking_enabled else "disabled",
            "timer": self._blocking_timer,
        }

    async def set_blocking(self, enabled: bool, timer: int | None = None) -> dict[str, Any]:
        self._blocking_enabled = enabled
        self._blocking_timer = timer if not enabled and timer else None
        return await self.get_blocking()

    # ── Query Log ─────────────────────────────────────────────────────

    async def get_queries(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        domains = [
            "google.com", "github.com", "reddit.com", "ads.google.com",
            "tracking.facebook.com", "api.github.com", "cdn.jsdelivr.net",
            "analytics.google.com", "telemetry.mozilla.org", "example.com",
            "fonts.googleapis.com", "cloudflare.com", "amazon.com",
        ]
        statuses = ["FORWARDED", "BLOCKED", "CACHED", "FORWARDED", "FORWARDED", "CACHED"]
        query_types = ["A", "AAAA", "A", "A", "AAAA", "HTTPS"]
        clients = ["192.168.1.10", "192.168.1.20", "192.168.1.30", "10.8.0.2", "192.168.1.100"]

        now = time.time()
        queries = []
        for i in range(limit):
            domain = random.choice(domains)
            s = random.choice(statuses)
            queries.append({
                "timestamp": now - (offset + i) * 2.5,
                "domain": domain,
                "client": random.choice(clients),
                "query_type": random.choice(query_types),
                "status": s,
                "reply_type": "IP" if s == "FORWARDED" else ("NXDOMAIN" if s == "BLOCKED" else "CACHE"),
                "response_time": round(random.uniform(0.5, 150.0), 1),
            })
        return {"queries": queries, "total": 50000}

    # ── Statistics ────────────────────────────────────────────────────

    async def get_top_domains(self, count: int = 10) -> dict[str, Any]:
        domains = [
            ("google.com", 4520), ("github.com", 3200), ("cdn.jsdelivr.net", 2800),
            ("fonts.googleapis.com", 2100), ("api.github.com", 1800),
            ("cloudflare.com", 1500), ("reddit.com", 1200), ("amazon.com", 900),
            ("stackoverflow.com", 750), ("wikipedia.org", 600),
        ]
        return {"top_permitted": [{"domain": d, "count": c} for d, c in domains[:count]]}

    async def get_top_blocked(self, count: int = 10) -> dict[str, Any]:
        domains = [
            ("ads.google.com", 3100), ("tracking.facebook.com", 2400),
            ("analytics.google.com", 1900), ("telemetry.mozilla.org", 1500),
            ("pixel.facebook.com", 1200), ("ad.doubleclick.net", 950),
            ("pagead2.googlesyndication.com", 800), ("graph.facebook.com", 650),
            ("connect.facebook.net", 500), ("static.ads-twitter.com", 350),
        ]
        return {"top_blocked": [{"domain": d, "count": c} for d, c in domains[:count]]}

    async def get_top_clients(self, count: int = 10) -> dict[str, Any]:
        clients = [
            ("192.168.1.10", "desktop-pc", 15000),
            ("192.168.1.20", "laptop", 8500),
            ("192.168.1.30", "phone", 5200),
            ("10.8.0.2", "vpn-client", 3100),
            ("192.168.1.100", "nas", 2000),
        ]
        return {
            "top_clients": [
                {"client": ip, "name": name, "count": c}
                for ip, name, c in clients[:count]
            ]
        }

    async def get_history(self) -> dict[str, Any]:
        now = time.time()
        history = []
        for i in range(144):  # 24h in 10-min intervals
            ts = now - (143 - i) * 600
            total = random.randint(200, 800)
            blocked = int(total * random.uniform(0.15, 0.35))
            history.append({"timestamp": ts, "total": total, "blocked": blocked})
        return {"history": history}

    # ── Domain Management ─────────────────────────────────────────────

    async def get_domains(self, list_type: str, kind: str) -> dict[str, Any]:
        key = f"{list_type}_{kind}"
        return {"domains": self._domains.get(key, [])}

    async def add_domain(self, list_type: str, kind: str, domain: str, comment: str = "") -> dict[str, Any]:
        key = f"{list_type}_{kind}"
        self._next_domain_id += 1
        entry = {"id": self._next_domain_id, "domain": domain, "comment": comment, "enabled": True}
        self._domains.setdefault(key, []).append(entry)
        return {"success": True, "domain": entry}

    async def remove_domain(self, list_type: str, kind: str, domain: str) -> dict[str, Any]:
        key = f"{list_type}_{kind}"
        before = len(self._domains.get(key, []))
        self._domains[key] = [d for d in self._domains.get(key, []) if d["domain"] != domain]
        removed = before - len(self._domains[key])
        return {"success": removed > 0, "removed": removed}

    # ── Adlist Management ─────────────────────────────────────────────

    async def get_adlists(self) -> dict[str, Any]:
        return {"lists": self._adlists}

    async def add_adlist(self, url: str, comment: str = "") -> dict[str, Any]:
        self._next_adlist_id += 1
        entry = {"id": self._next_adlist_id, "url": url, "comment": comment, "enabled": True, "number": 0}
        self._adlists.append(entry)
        return {"success": True, "list": entry}

    async def remove_adlist(self, address: str) -> dict[str, Any]:
        before = len(self._adlists)
        self._adlists = [a for a in self._adlists if a.get("url") != address]
        return {"success": before != len(self._adlists)}

    async def toggle_adlist(self, address: str, enabled: bool) -> dict[str, Any]:
        for a in self._adlists:
            if a.get("url") == address:
                a["enabled"] = enabled
                return {"success": True}
        return {"success": False}

    async def update_gravity(self) -> dict[str, Any]:
        return {"success": True, "message": "Gravity update simulated (dev mode)"}

    # ── Local DNS ─────────────────────────────────────────────────────

    async def get_local_dns(self) -> dict[str, Any]:
        return {"records": self._local_dns}

    async def add_local_dns(self, domain: str, ip: str) -> dict[str, Any]:
        # Remove existing entry for same domain
        self._local_dns = [r for r in self._local_dns if r["domain"] != domain]
        self._local_dns.append({"domain": domain, "ip": ip})
        return {"success": True}

    async def remove_local_dns(self, domain: str, ip: str) -> dict[str, Any]:
        before = len(self._local_dns)
        self._local_dns = [r for r in self._local_dns if r["domain"] != domain]
        return {"success": before != len(self._local_dns)}

    # ── Actions ───────────────────────────────────────────────────────

    async def restart_dns(self) -> dict[str, Any]:
        return {"success": True, "message": "DNS resolver restarted (dev mode)"}

    # ── Container Lifecycle (no-op in dev) ────────────────────────────

    async def deploy_container(self, config: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "message": "Container deployment simulated (dev mode)", "container_status": "running"}

    async def start_container(self) -> dict[str, Any]:
        return {"success": True, "message": "Container start simulated (dev mode)", "container_status": "running"}

    async def stop_container(self) -> dict[str, Any]:
        return {"success": True, "message": "Container stop simulated (dev mode)", "container_status": "exited"}

    async def remove_container(self) -> dict[str, Any]:
        return {"success": True, "message": "Container removal simulated (dev mode)", "container_status": None}

    async def update_container(self) -> dict[str, Any]:
        return {"success": True, "message": "Container update simulated (dev mode)", "container_status": "running"}

    async def get_container_logs(self, lines: int = 100) -> dict[str, Any]:
        log_lines = [
            "[2026-02-27 08:00:01.123] FTL started!",
            "[2026-02-27 08:00:01.456] Loading gravity database...",
            "[2026-02-27 08:00:02.789] Gravity database loaded (106542 domains)",
            "[2026-02-27 08:00:02.800] DNS service started",
            "[2026-02-27 08:00:03.100] Blocking enabled with 106542 domains on blocklist",
            "[2026-02-27 08:00:03.200] Ready",
        ]
        return {"logs": "\n".join(log_lines), "lines": len(log_lines)}
