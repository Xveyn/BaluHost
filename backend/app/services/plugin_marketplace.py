"""Marketplace service: fetches the upstream ``index.json``, caches it, and
drives install/uninstall via :class:`PluginInstaller`.

This is the thin service layer that routes delegate to. It owns:

* the in-memory index cache (TTL-based)
* the HTTP fetcher for ``index.json`` (separate from the one used for plugin
  archives, so tests can mock just the index)
* a single :class:`PluginInstaller` instance configured with the real plugins
  directory and core versions snapshot

The actual install pipeline (download → checksum → extract → resolver → pip →
atomic swap) lives in :mod:`app.plugins.installer`; this file just wires
things together.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from pydantic import ValidationError

from app.plugins.core_versions import CoreVersions, CoreVersionsError, load_core_versions
from app.plugins.installer import (
    InstalledArtifact,
    PluginInstaller,
)
from app.plugins.marketplace import (
    SUPPORTED_INDEX_VERSIONS,
    MarketplaceEntry,
    MarketplaceIndex,
    MarketplaceVersionEntry,
)
from app.plugins.resolver import InstalledPluginRequirement

logger = logging.getLogger(__name__)

IndexFetcher = Callable[[str], bytes]


class MarketplaceError(Exception):
    """Base error for marketplace service operations."""


class IndexFetchError(MarketplaceError):
    """Could not download ``index.json``."""


class IndexParseError(MarketplaceError):
    """``index.json`` was not valid JSON or did not match the schema."""


class PluginNotFoundError(MarketplaceError):
    """The requested plugin (or version) is not in the marketplace index."""


@dataclass
class CachedIndex:
    index: MarketplaceIndex
    fetched_at: float


def _default_index_fetcher(url: str) -> bytes:
    import httpx

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


class MarketplaceService:
    """Fetches the marketplace index and delegates install/uninstall.

    Parameters
    ----------
    index_url:
        URL of the upstream ``index.json``.
    installer:
        A fully-wired :class:`PluginInstaller` that knows the real plugins
        directory and core versions. Tests inject a fake installer with an
        in-memory fetcher and no-op pip runner.
    index_fetcher:
        Callable fetching ``index.json`` bytes. Defaults to an ``httpx``-based
        fetcher. Distinct from the installer's artifact fetcher.
    cache_ttl:
        Seconds to cache a successful index fetch.
    """

    def __init__(
        self,
        *,
        index_url: str,
        installer: PluginInstaller,
        index_fetcher: Optional[IndexFetcher] = None,
        cache_ttl: int = 300,
    ) -> None:
        self._index_url = index_url
        self._installer = installer
        self._fetch = index_fetcher or _default_index_fetcher
        self._cache_ttl = cache_ttl
        self._cache: Optional[CachedIndex] = None

    @property
    def plugins_dir(self) -> Path:
        return self._installer.plugins_dir

    @property
    def core_versions(self) -> CoreVersions:
        return self._installer.core_versions

    def get_index(self, *, force_refresh: bool = False) -> MarketplaceIndex:
        """Return the (possibly cached) marketplace index.

        Fetches from ``index_url`` if there is no cache entry, the cache is
        stale, or ``force_refresh`` is set.
        """
        now = time.monotonic()
        if (
            not force_refresh
            and self._cache is not None
            and (now - self._cache.fetched_at) < self._cache_ttl
        ):
            return self._cache.index

        try:
            raw = self._fetch(self._index_url)
        except Exception as exc:
            raise IndexFetchError(
                f"failed to fetch marketplace index from {self._index_url}: {exc}"
            ) from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IndexParseError(f"marketplace index is not valid JSON: {exc}") from exc

        try:
            index = MarketplaceIndex.model_validate(payload)
        except ValidationError as exc:
            raise IndexParseError(
                f"marketplace index failed schema validation: {exc}"
            ) from exc

        if index.index_version not in SUPPORTED_INDEX_VERSIONS:
            raise IndexParseError(
                f"unsupported index_version {index.index_version!r} "
                f"(supported: {sorted(SUPPORTED_INDEX_VERSIONS)})"
            )

        self._cache = CachedIndex(index=index, fetched_at=now)
        return index

    def invalidate_cache(self) -> None:
        self._cache = None

    def get_plugin(self, name: str) -> MarketplaceEntry:
        index = self.get_index()
        entry = index.get_plugin(name)
        if entry is None:
            raise PluginNotFoundError(f"plugin {name!r} not in marketplace")
        return entry

    def get_version_entry(
        self, name: str, version: Optional[str] = None
    ) -> MarketplaceVersionEntry:
        plugin = self.get_plugin(name)
        target = version or plugin.latest_version
        ver = plugin.get_version(target)
        if ver is None:
            raise PluginNotFoundError(
                f"plugin {name!r} has no version {target!r} "
                f"(available: {[v.version for v in plugin.versions]})"
            )
        return ver

    def install(
        self,
        name: str,
        *,
        version: Optional[str] = None,
        installed: Sequence[InstalledPluginRequirement] = (),
        force: bool = False,
    ) -> InstalledArtifact:
        """Install the given plugin by name + (optional) version.

        If ``version`` is omitted the marketplace's ``latest_version`` is used.
        ``installed`` is the list of *other* already-installed plugins whose
        pinned dependencies must be cross-checked by the resolver.
        """
        entry = self.get_version_entry(name, version)
        return self._installer.install(
            entry, name, installed=installed, force=force
        )

    def uninstall(self, name: str) -> bool:
        return self._installer.uninstall(name)


_instance: Optional[MarketplaceService] = None


def get_marketplace_service() -> MarketplaceService:
    """FastAPI dependency: return a lazily-built singleton service.

    Uses ``settings.plugins_marketplace_index_url`` and the configured
    external plugins directory. Tests should override this via
    ``app.dependency_overrides``.

    Raises a 503 ``HTTPException`` if the plugins directory cannot be
    created (permission denied, read-only FS, …) or the Core versions
    snapshot cannot be loaded — so operators see a clear reason instead
    of a bare 500 traceback.
    """
    from fastapi import HTTPException, status

    global _instance
    if _instance is not None:
        return _instance

    from app.core.config import settings

    plugins_dir = Path(settings.plugins_external_dir)
    try:
        plugins_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error(
            "plugin marketplace disabled: cannot create plugins dir %s: %s",
            plugins_dir,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"plugin marketplace unavailable: plugins directory "
                f"{plugins_dir} is not writable by the backend service user "
                f"({exc.strerror or exc}). Create the directory and chown it "
                f"to the service user."
            ),
        ) from exc

    try:
        core_versions = load_core_versions()
    except CoreVersionsError as exc:
        logger.error("plugin marketplace disabled: cannot load core_versions.json: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"plugin marketplace unavailable: core_versions.json could not be loaded ({exc})",
        ) from exc

    installer = PluginInstaller(
        plugins_dir=plugins_dir,
        core_versions=core_versions,
    )
    _instance = MarketplaceService(
        index_url=settings.plugins_marketplace_index_url,
        installer=installer,
        cache_ttl=settings.plugins_marketplace_cache_ttl,
    )
    return _instance


def reset_marketplace_service() -> None:
    """Test hook: drop the cached singleton so the next call rebuilds it."""
    global _instance
    _instance = None
