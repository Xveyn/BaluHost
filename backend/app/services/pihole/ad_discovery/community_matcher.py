"""Community blocklist matcher — downloads, caches, and matches domains against public blocklists."""

from __future__ import annotations

import gzip
import ipaddress
import logging
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Disk cache directory
_CACHE_DIR = Path(__file__).resolve().parents[4] / "data" / "ad_discovery_cache"
_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
_DOWNLOAD_TIMEOUT_S = 60


# Dev mode: well-known ad/tracker domains for testing without network
_DEV_MODE_DOMAINS: set[str] = {
    # Ads
    "ad.doubleclick.net",
    "adservice.google.com",
    "pagead2.googlesyndication.com",
    "googleads.g.doubleclick.net",
    "ads.facebook.com",
    "an.facebook.com",
    "ads.yahoo.com",
    "ads.twitter.com",
    "ads.linkedin.com",
    "ads.reddit.com",
    "advertising.amazon.com",
    "aax.amazon-adsystem.com",
    "adsrvr.org",
    "adnxs.com",
    "rubiconproject.com",
    "pubmatic.com",
    "openx.net",
    "casalemedia.com",
    "criteo.com",
    "criteo.net",
    "moatads.com",
    "serving-sys.com",
    "adform.net",
    "bidswitch.net",
    "smartadserver.com",
    "media.net",
    "outbrain.com",
    "taboola.com",
    "revcontent.com",
    "mgid.com",
    # Tracking
    "tracking.example.com",
    "tracker.unity3d.com",
    "pixel.facebook.com",
    "pixel.adsafeprotected.com",
    "beacon.krxd.net",
    "collect.tealiumiq.com",
    "telemetry.microsoft.com",
    "telemetry.mozilla.org",
    "clickstream.hearst.com",
    "sb.scorecardresearch.com",
    "b.scorecardresearch.com",
    "pixel.quantserve.com",
    "pixel.wp.com",
    "bat.bing.com",
    "ct.pinterest.com",
    "t.co",
    "analytics.tiktok.com",
    "tr.snapchat.com",
    # Analytics
    "analytics.google.com",
    "stats.wp.com",
    "stats.g.doubleclick.net",
    "metrics.icloud.com",
    "segment.io",
    "cdn.segment.com",
    "api.segment.io",
    "hotjar.com",
    "static.hotjar.com",
    "script.hotjar.com",
    "mouseflow.com",
    "cdn.mouseflow.com",
    "heapanalytics.com",
    "cdn.heapanalytics.com",
    "mixpanel.com",
    "cdn.mxpnl.com",
    "amplitude.com",
    "api.amplitude.com",
    "fullstory.com",
    "rs.fullstory.com",
    "plausible.io",
    # Fingerprinting
    "fingerprint.com",
    "fpjs.io",
    "browser-update.org",
    "device-api.smartadserver.com",
    # Other common ad domains
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices.com",
    "googletagmanager.com",
    "googletagservices.com",
    "2mdn.net",
    "admob.com",
    "adsymptotic.com",
    "adtechus.com",
    "advertising.com",
    "agkn.com",
    "atdmt.com",
    "bluekai.com",
    "btrll.com",
    "contextweb.com",
    "dotomi.com",
    "everesttech.net",
    "eyereturn.com",
    "flashtalking.com",
    "fls.doubleclick.net",
    "intellitxt.com",
    "liadm.com",
    "mathtag.com",
    "mookie1.com",
    "nexac.com",
    "quantcast.com",
    "richrelevance.com",
    "rlcdn.com",
    "turn.com",
    "yieldmanager.com",
}


@dataclass
class MatchResult:
    """Result of matching a domain against community lists."""

    domain: str
    hits: int = 0
    matched_lists: list[str] = field(default_factory=list)


def _validate_url(url: str) -> None:
    """Validate URL: https-only, no private/loopback IPs.

    Raises ValueError if the URL is not HTTPS or resolves to a private/reserved address.
    This prevents SSRF attacks via user-supplied blocklist URLs.
    """
    if not url.startswith("https://"):
        raise ValueError(f"Only HTTPS URLs are allowed, got: {url[:50]}")

    # Extract hostname from URL
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("Could not extract hostname from URL")
    except Exception as e:
        raise ValueError(f"Invalid URL: {e}") from e

    # Resolve and check for private IPs (SSRF protection)
    try:
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            addr = info[4][0]
            ip = ipaddress.ip_address(addr)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError(f"URL resolves to private/reserved IP: {addr}")
    except socket.gaierror:
        raise ValueError(f"Could not resolve hostname: {hostname}")


def _parse_list_content(text: str) -> set[str]:
    """Parse blocklist content into a set of domains.

    Handles:
    - Domain-per-line format
    - Hosts format (0.0.0.0 domain.com or 127.0.0.1 domain.com)
    - Comments (lines starting with #)
    - Blank lines
    - Inline comments after domain entries
    """
    domains: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Hosts format: "0.0.0.0 domain.com" or "127.0.0.1 domain.com"
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1"):
            domain = parts[1].strip().lower()
            # Strip inline comments
            if "#" in domain:
                domain = domain.split("#")[0].strip()
            if domain and domain != "localhost":
                domains.add(domain)
        elif len(parts) >= 1:
            # Domain-per-line format (also handles trailing inline comments)
            domain = parts[0].lower()
            if "#" in domain:
                domain = domain.split("#")[0].strip()
            if domain:
                domains.add(domain)

    return domains


class CommunityMatcher:
    """Downloads, caches, and matches domains against community blocklists.

    Uses gzip disk cache to avoid redundant downloads. In-memory sets provide
    O(1) per-domain lookup. SSRF protection is enforced on all download URLs.
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self._lists: dict[int, set[str]] = {}
        self._list_names: dict[int, str] = {}
        self._cache_dir = cache_dir or _CACHE_DIR

    def load_sets(self, list_id: int, name: str, domains: set[str]) -> None:
        """Load a domain set directly (for tests or manual injection)."""
        self._lists[list_id] = domains
        self._list_names[list_id] = name

    async def fetch_list(self, list_id: int, url: str, name: str) -> int:
        """Download a blocklist, parse it, cache to disk, and load into memory.

        Args:
            list_id: Database ID used as cache filename key.
            url: HTTPS URL to the blocklist. SSRF validation is enforced.
            name: Human-readable list name stored for match reporting.

        Returns:
            Number of unique domains parsed.

        Raises:
            ValueError: If the URL fails SSRF validation or content exceeds size limit.
            httpx.HTTPError: If the download fails.
        """
        # Dev mode: use hardcoded domains instead of downloading
        try:
            from app.core.config import settings
            if settings.is_dev_mode:
                domains = _DEV_MODE_DOMAINS.copy()
                # Cache and load into memory as normal
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                cache_path = self._cache_dir / f"{list_id}.gz"
                with gzip.open(cache_path, "wt", encoding="utf-8") as f:
                    f.write("\n".join(sorted(domains)))
                self._lists[list_id] = domains
                self._list_names[list_id] = name
                logger.debug("Dev mode: loaded %d mock domains for %r", len(domains), name)
                return len(domains)
        except ImportError:
            pass

        _validate_url(url)

        async with httpx.AsyncClient(
            timeout=_DOWNLOAD_TIMEOUT_S, follow_redirects=True
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            if len(response.content) > _MAX_DOWNLOAD_BYTES:
                raise ValueError(
                    f"Download exceeds {_MAX_DOWNLOAD_BYTES} bytes limit"
                )

            text = response.text

        domains = _parse_list_content(text)

        # Cache to disk as gzip
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self._cache_dir / f"{list_id}.gz"
        with gzip.open(cache_path, "wt", encoding="utf-8") as f:
            f.write("\n".join(sorted(domains)))

        # Load into memory
        self._lists[list_id] = domains
        self._list_names[list_id] = name

        logger.debug("Fetched list %r (id=%d): %d domains", name, list_id, len(domains))
        return len(domains)

    def load_from_cache(self, list_id: int, name: str) -> int:
        """Load a cached list from disk into memory.

        Args:
            list_id: Database ID used as cache filename key.
            name: Human-readable list name stored for match reporting.

        Returns:
            Number of domains loaded (0 if cache file does not exist).
        """
        cache_path = self._cache_dir / f"{list_id}.gz"
        if not cache_path.exists():
            return 0

        with gzip.open(cache_path, "rt", encoding="utf-8") as f:
            content = f.read()

        domains = {line.strip() for line in content.splitlines() if line.strip()}
        self._lists[list_id] = domains
        self._list_names[list_id] = name
        return len(domains)

    def save_to_cache(self, list_id: int) -> None:
        """Persist the current in-memory domain set to disk as gzip."""
        if list_id not in self._lists:
            return
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self._cache_dir / f"{list_id}.gz"
        with gzip.open(cache_path, "wt", encoding="utf-8") as f:
            f.write("\n".join(sorted(self._lists[list_id])))

    async def refresh_all(self, db) -> None:
        """Refresh all enabled reference lists that are past their fetch interval.

        For each enabled list:
        - If still fresh (within fetch_interval_hours): load from cache if not in memory.
        - If stale or never fetched: download, parse, cache, and update DB record.
        - On download failure: log error, fall back to cached version if available.
        """
        from datetime import datetime, timedelta, timezone

        from app.models.ad_discovery import AdDiscoveryReferenceList

        lists = (
            db.query(AdDiscoveryReferenceList)
            .filter(AdDiscoveryReferenceList.enabled == True)  # noqa: E712
            .all()
        )

        now = datetime.now(timezone.utc)
        for ref_list in lists:
            if ref_list.last_fetched_at is not None:
                fetched = ref_list.last_fetched_at
                if fetched.tzinfo is None:
                    fetched = fetched.replace(tzinfo=timezone.utc)
                age = now - fetched
                if age < timedelta(hours=ref_list.fetch_interval_hours):
                    # Still fresh — load from cache if not already in memory
                    if ref_list.id not in self._lists:
                        loaded = self.load_from_cache(ref_list.id, ref_list.name)
                        if loaded:
                            logger.debug(
                                "Loaded fresh cache for %r: %d domains",
                                ref_list.name,
                                loaded,
                            )
                    continue

            # Stale or never fetched — download now
            try:
                count = await self.fetch_list(ref_list.id, ref_list.url, ref_list.name)
                ref_list.domain_count = count
                ref_list.last_fetched_at = now
                ref_list.last_error = None
                ref_list.last_error_at = None
                db.commit()
                logger.info(
                    "Refreshed reference list %r: %d domains", ref_list.name, count
                )
            except Exception as e:
                ref_list.last_error = str(e)[:500]
                ref_list.last_error_at = now
                db.commit()
                logger.warning("Failed to refresh %r: %s", ref_list.name, e)
                # Fall back to disk cache if available
                if ref_list.id not in self._lists:
                    fallback = self.load_from_cache(ref_list.id, ref_list.name)
                    if fallback:
                        logger.info(
                            "Using stale cache for %r: %d domains",
                            ref_list.name,
                            fallback,
                        )

    def match_domain(self, domain: str) -> MatchResult:
        """Check if a domain appears in any loaded reference lists.

        Args:
            domain: Domain to look up (case-insensitive).

        Returns:
            MatchResult with hit count and names of all matched lists.
        """
        domain_lower = domain.lower()
        matched: list[str] = []

        for list_id, domain_set in self._lists.items():
            if domain_lower in domain_set:
                matched.append(self._list_names.get(list_id, f"List #{list_id}"))

        return MatchResult(domain=domain, hits=len(matched), matched_lists=matched)

    def match_domains(self, domains: list[str]) -> list[MatchResult]:
        """Batch-match a list of domains against all loaded reference lists.

        Args:
            domains: List of domains to check.

        Returns:
            List of MatchResult objects, one per input domain, in the same order.
        """
        return [self.match_domain(d) for d in domains]


# Module-level singleton — shared across all callers in the same process
_matcher = CommunityMatcher()


def get_community_matcher() -> CommunityMatcher:
    """Return the module-level CommunityMatcher singleton."""
    return _matcher
