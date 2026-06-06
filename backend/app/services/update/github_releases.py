"""GitHub Releases client + positional aggregation helpers for the update page.

GitHub's `/releases` API returns newest-first; all range logic here is positional
(not semver-ordered) so it is robust against `-pre.N` suffix ordering quirks.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings
from app.services.update.utils import parse_version

GITHUB_API = "https://api.github.com"


class GitHubUnavailable(Exception):
    """Raised when GitHub releases cannot be fetched (network / rate-limit / HTTP error)."""


@dataclass
class GitHubRelease:
    tag: str
    name: str
    body_markdown: str
    prerelease: bool
    published_at: Optional[str]
    url: str


class GitHubReleasesClient:
    """Fetches the releases list with a per-instance TTL cache."""

    def __init__(self, repo: Optional[str] = None, ttl_seconds: int = 900):
        self.repo = repo or settings.update_github_repo
        self.ttl = ttl_seconds
        self._cache: Optional[list[GitHubRelease]] = None
        self._cached_at: float = 0.0

    async def list_releases(self, *, force: bool = False) -> list[GitHubRelease]:
        now = time.monotonic()
        if not force and self._cache is not None and (now - self._cached_at) < self.ttl:
            return self._cache

        url = f"{GITHUB_API}/repos/{self.repo}/releases"
        headers = {"User-Agent": "BaluHost", "Accept": "application/vnd.github+json"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers, params={"per_page": 100})
            if resp.status_code != 200:
                raise GitHubUnavailable(f"GitHub returned HTTP {resp.status_code}")
            data = resp.json()
        except GitHubUnavailable:
            raise
        except Exception as exc:  # httpx errors, JSON decode, etc.
            raise GitHubUnavailable(str(exc)) from exc

        releases = [
            GitHubRelease(
                tag=r.get("tag_name", ""),
                name=r.get("name") or r.get("tag_name", ""),
                body_markdown=r.get("body") or "",
                prerelease=bool(r.get("prerelease")),
                published_at=r.get("published_at"),
                url=r.get("html_url", ""),
            )
            for r in (data or [])
            if r.get("tag_name")
        ]
        self._cache = releases
        self._cached_at = now
        return releases


def filter_channel(releases: list[GitHubRelease], channel: str) -> list[GitHubRelease]:
    if channel == "unstable":
        return list(releases)
    return [r for r in releases if not r.prerelease]


def latest_for_channel(releases: list[GitHubRelease], channel: str) -> Optional[GitHubRelease]:
    """Newest release in the channel (the list is already newest-first)."""
    filtered = filter_channel(releases, channel)
    return filtered[0] if filtered else None


def _find_index(releases: list[GitHubRelease], version: str) -> Optional[int]:
    target = parse_version(version)
    for i, r in enumerate(releases):
        if parse_version(r.tag) == target:
            return i
    return None


def notes_since_last_stable(
    releases: list[GitHubRelease], up_to_version: str
) -> tuple[list[GitHubRelease], Optional[str]]:
    """Releases for the running version's notes "since the last stable", newest first.

    - If up_to is stable: just [up_to] (its body already covers since-last-stable).
    - If up_to is a pre-release: up_to plus older pre-releases, down to (excl.) the
      first older stable.
    Returns (slice, since_tag).
    """
    idx = _find_index(releases, up_to_version)
    if idx is None:
        return [], None
    up = releases[idx]
    # the first stable strictly older than up_to (for the since_version label)
    since_tag = next((r.tag for r in releases[idx + 1:] if not r.prerelease), None)
    if not up.prerelease:
        return [up], since_tag
    out: list[GitHubRelease] = []
    for r in releases[idx:]:
        if not r.prerelease:
            break
        out.append(r)
    return out, since_tag


def releases_between(
    releases: list[GitHubRelease], newer_than: str, up_to: str
) -> list[GitHubRelease]:
    """Releases from up_to (inclusive) down to newer_than (exclusive), newest first."""
    up_idx = _find_index(releases, up_to)
    nt_idx = _find_index(releases, newer_than)
    start = up_idx if up_idx is not None else 0
    # When the running version isn't a published release (local dev build, or
    # aged past the fetched page), don't return the whole history as the delta —
    # show just the target release's notes.
    end = nt_idx if nt_idx is not None else start + 1
    if start >= end:
        return []
    return releases[start:end]
