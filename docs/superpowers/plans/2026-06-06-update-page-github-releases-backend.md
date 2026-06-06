# Update Page → GitHub Releases — Backend Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make GitHub Releases the source for the update page's release-notes, the "update available?" check, and the releases list (curated markdown bodies), with a CHANGELOG.md offline fallback; remove the dead `development`-branch logic. Git/systemd still applies updates.

**Architecture:** A new `GitHubReleasesClient` (httpx + per-worker TTL cache) plus pure, positional helpers feed `ProdUpdateBackend.get_release_notes/check_for_updates/get_all_releases`. Notes aggregate "since the last stable" using the API's newest-first ordering (no fragile semver ordering of `-pre.N`). On any GitHub error → parse the bundled `CHANGELOG.md`.

**Tech Stack:** FastAPI, httpx, Pydantic, Pytest.

Spec: `docs/superpowers/specs/2026-06-06-update-page-github-releases-design.md`. Frontend (markdown rendering, dev-channel UI removal, i18n) is **Plan 2**.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `backend/app/core/config.py` | settings | +`update_github_repo`, +`update_changelog_path` |
| `backend/app/schemas/update.py` | contracts | reshape `ReleaseNotesResponse`, +`ReleaseNoteItem`, +`ChangelogEntry.body_markdown`, extend `ReleaseInfo`, drop `DevUpdateStartRequest`, drop `UpdateCheckResponse.dev_*` |
| `backend/app/services/update/github_releases.py` | GitHub client + positional helpers | NEW |
| `backend/app/services/update/changelog_fallback.py` | CHANGELOG.md parser | NEW |
| `backend/app/services/update/prod_backend.py` | release-notes/check/releases via GitHub | rework + drop `check_dev_branch` |
| `backend/app/services/update/dev_backend.py` | mock markdown notes | rework + drop `check_dev_branch` |
| `backend/app/services/update/backend.py` | abstract interface | drop `check_dev_branch` |
| `backend/app/services/update/service.py` | orchestration | drop dev_* in `check_for_updates`, drop `start_dev_update` |
| `backend/app/api/routes/updates.py` | HTTP | drop `POST /updates/start-dev` |
| `backend/tests/services/test_github_releases.py`, `test_changelog_fallback.py`, `test_update_github.py` | tests | NEW |

---

## Task 1: Config + schema reshape

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/schemas/update.py`
- Test: `backend/tests/services/test_update_github.py`

- [ ] **Step 1: Add settings**

In `backend/app/core/config.py`, inside the `Settings` class (place near other feature settings, mirroring the existing `Field(default=..., validation_alias="...")` style):

```python
    update_github_repo: str = Field(
        default="Xveyn/BaluHost",
        validation_alias="BALUHOST_UPDATE_GITHUB_REPO",
        description="owner/repo used to read GitHub Releases for the update page.",
    )
    update_changelog_path: str = Field(
        default="CHANGELOG.md",
        validation_alias="BALUHOST_UPDATE_CHANGELOG_PATH",
        description="Path (repo-root-relative or absolute) to the bundled CHANGELOG.md fallback.",
    )
```

(If `Field` is not already imported in `config.py`, it is — the existing settings use it.)

- [ ] **Step 2: Write the failing schema test**

Create `backend/tests/services/test_update_github.py`:

```python
from app.schemas.update import ReleaseNoteItem, ReleaseNotesResponse, ReleaseInfo, ChangelogEntry


def test_release_notes_response_shape():
    item = ReleaseNoteItem(version="1.36.0", is_prerelease=False, url="u", body_markdown="### Added\n- x")
    resp = ReleaseNotesResponse(current_version="1.36.0", since_version="1.35.0", source="github", releases=[item])
    assert resp.source == "github"
    assert resp.releases[0].body_markdown.startswith("### Added")


def test_changelog_entry_has_body_markdown():
    e = ChangelogEntry(version="1.36.0", body_markdown="- y")
    assert e.body_markdown == "- y"


def test_release_info_extended_optional_commit():
    r = ReleaseInfo(tag="v1.36.0", version="1.36.0", is_prerelease=False)
    assert r.commit_short is None and r.html_url is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_update_github.py -v --no-cov`
Expected: FAIL — `ImportError: ReleaseNoteItem` / unexpected required field `commit_short`.

- [ ] **Step 4: Reshape the schemas**

In `backend/app/schemas/update.py`:

(a) Add `ReleaseNoteItem` and reshape `ReleaseNotesResponse` — replace the existing
`ReleaseNoteCategory` + `ReleaseNotesResponse` block with:

```python
class ReleaseNoteCategory(BaseModel):
    """Legacy categorized release-note group (kept for compatibility; unused by GitHub path)."""

    name: str
    icon: str
    changes: list[str] = Field(default_factory=list)


class ReleaseNoteItem(BaseModel):
    """A single release's curated notes (one GitHub release / CHANGELOG section)."""

    version: str = Field(description="Version, e.g. '1.36.0' or '1.35.1-pre.3'")
    date: Optional[datetime] = Field(default=None, description="Release date")
    is_prerelease: bool = Field(default=False)
    url: Optional[str] = Field(default=None, description="Release HTML URL")
    body_markdown: str = Field(default="", description="Curated release notes (markdown)")


class ReleaseNotesResponse(BaseModel):
    """Release notes since the last stable, newest first."""

    current_version: str
    since_version: Optional[str] = Field(default=None, description="The last stable the notes start from")
    source: Literal["github", "changelog"] = "github"
    releases: list[ReleaseNoteItem] = Field(default_factory=list)
```

(b) In `ChangelogEntry`, add after `is_prerelease`:

```python
    body_markdown: Optional[str] = Field(default=None, description="Curated release notes (markdown)")
```

(c) In `ReleaseInfo`, replace the class body with (adds `name`/`html_url`/`body_markdown`, makes `commit_short` optional):

```python
    tag: str = Field(description="Git tag (e.g., 'v1.36.0')")
    version: str = Field(description="Version string without 'v' prefix")
    date: Optional[str] = Field(default=None, description="Release date (ISO 8601)")
    is_prerelease: bool = Field(default=False)
    commit_short: Optional[str] = Field(default=None, description="Short commit hash (git path only)")
    name: Optional[str] = Field(default=None, description="Release name")
    html_url: Optional[str] = Field(default=None, description="Release HTML URL")
    body_markdown: Optional[str] = Field(default=None, description="Curated release notes (markdown)")
```

(d) Delete the `DevUpdateStartRequest` class entirely.

(e) In `UpdateCheckResponse`, delete the four dev-branch fields (`dev_version_available`,
`dev_version`, `dev_commits_ahead`, `dev_commits`) and their `CommitInfo` forward use.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/services/test_update_github.py -v --no-cov`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/app/schemas/update.py backend/tests/services/test_update_github.py
git commit -m "feat(updates): GitHub-releases settings + reshape release-notes schemas"
```

---

## Task 2: GitHub Releases client + positional helpers

**Files:**
- Create: `backend/app/services/update/github_releases.py`
- Test: `backend/tests/services/test_github_releases.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/test_github_releases.py`:

```python
import pytest

from app.services.update.github_releases import (
    GitHubRelease, GitHubReleasesClient, GitHubUnavailable,
    filter_channel, latest_for_channel, notes_since_last_stable, releases_between,
)


def _r(tag, prerelease, body="b"):
    return GitHubRelease(tag=tag, name=tag, body_markdown=body, prerelease=prerelease,
                         published_at=None, url=f"https://x/{tag}")


# Newest-first, like the GitHub API returns.
RELEASES = [
    _r("v1.36.0", False),
    _r("v1.35.1-pre.25", True),
    _r("v1.35.1-pre.24", True),
    _r("v1.35.0", False),
    _r("v1.34.0", False),
]


def test_filter_channel():
    assert len(filter_channel(RELEASES, "unstable")) == 5
    assert [r.tag for r in filter_channel(RELEASES, "stable")] == ["v1.36.0", "v1.35.0", "v1.34.0"]


def test_latest_for_channel():
    assert latest_for_channel(RELEASES, "stable").tag == "v1.36.0"
    assert latest_for_channel(RELEASES, "unstable").tag == "v1.36.0"


def test_notes_since_last_stable_for_prerelease():
    items, since = notes_since_last_stable(RELEASES, "1.35.1-pre.25")
    # current is a pre-release: aggregate from it back to (excl.) the last stable v1.35.0
    assert [r.tag for r in items] == ["v1.35.1-pre.25", "v1.35.1-pre.24"]
    assert since == "v1.35.0"


def test_notes_since_last_stable_for_stable():
    items, since = notes_since_last_stable(RELEASES, "1.36.0")
    # current is stable: its own body already covers since-last-stable
    assert [r.tag for r in items] == ["v1.36.0"]
    assert since == "v1.35.0"


def test_releases_between_current_to_latest():
    # what an update from a pre-release to the latest stable brings
    items = releases_between(RELEASES, newer_than="1.35.1-pre.25", up_to="1.36.0")
    assert [r.tag for r in items] == ["v1.36.0"]


@pytest.mark.asyncio
async def test_list_releases_caches_and_falls_back(monkeypatch):
    client = GitHubReleasesClient(repo="x/y", ttl_seconds=999)
    calls = {"n": 0}

    class _Resp:
        status_code = 200
        def json(self):
            return [{"tag_name": "v1.0.0", "name": "v1.0.0", "body": "hi",
                     "prerelease": False, "published_at": "2026-01-01T00:00:00Z",
                     "html_url": "https://x/v1.0.0"}]

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k):
            calls["n"] += 1
            return _Resp()

    monkeypatch.setattr("app.services.update.github_releases.httpx.AsyncClient", _Client)
    first = await client.list_releases()
    second = await client.list_releases()
    assert first[0].tag == "v1.0.0"
    assert calls["n"] == 1  # second served from cache


@pytest.mark.asyncio
async def test_list_releases_raises_unavailable_on_error(monkeypatch):
    import httpx
    client = GitHubReleasesClient(repo="x/y")

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.services.update.github_releases.httpx.AsyncClient", _Client)
    with pytest.raises(GitHubUnavailable):
        await client.list_releases()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_github_releases.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: app.services.update.github_releases`.

- [ ] **Step 3: Implement the client + helpers**

Create `backend/app/services/update/github_releases.py`:

```python
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
    end = nt_idx if nt_idx is not None else len(releases)
    if start >= end:
        return []
    return releases[start:end]
```

- [ ] **Step 4: Add the asyncio marker dependency check**

The async tests use `@pytest.mark.asyncio`. Confirm it's available (the repo already uses
`pytest_asyncio` — see `conftest.py`). If a test errors with "async def functions are not natively
supported", add `import pytest_asyncio` is NOT needed; the repo's `pyproject` sets asyncio mode. Run
the tests as-is in the next step.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_github_releases.py -v --no-cov`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/update/github_releases.py backend/tests/services/test_github_releases.py
git commit -m "feat(updates): GitHub Releases client + positional since-last-stable helpers"
```

---

## Task 3: CHANGELOG.md fallback parser

**Files:**
- Create: `backend/app/services/update/changelog_fallback.py`
- Test: `backend/tests/services/test_changelog_fallback.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/test_changelog_fallback.py`:

```python
from app.services.update.changelog_fallback import parse_changelog, notes_since_last_stable_from_changelog

SAMPLE = """# Changelog

---

## [1.36.0] - 2026-06-06

### Added
- thing A

## [1.35.0] - 2026-05-01

### Fixed
- thing B
"""


def test_parse_changelog(tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(SAMPLE, encoding="utf-8")
    sections = parse_changelog(str(p))
    assert sections[0].version == "1.36.0"
    assert "thing A" in sections[0].body_markdown
    assert sections[1].version == "1.35.0"


def test_notes_for_current(tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(SAMPLE, encoding="utf-8")
    items, since = notes_since_last_stable_from_changelog(str(p), "1.36.0")
    assert items[0].version == "1.36.0"
    assert items[0].source_is_changelog if hasattr(items[0], "source_is_changelog") else True


def test_notes_missing_file(tmp_path):
    items, since = notes_since_last_stable_from_changelog(str(tmp_path / "nope.md"), "1.36.0")
    assert items == [] and since is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_changelog_fallback.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the parser**

Create `backend/app/services/update/changelog_fallback.py`:

```python
"""Offline fallback: parse the bundled CHANGELOG.md into release-note items.

Used when the GitHub Releases API is unavailable. CHANGELOG.md mainly holds
stable sections (`## [x.y.z] - date`), so this is a degraded-but-non-empty mode.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.schemas.update import ReleaseNoteItem
from app.services.update.utils import parse_version

_SECTION_RE = re.compile(r"^##\s*\[(?P<ver>[^\]]+)\]\s*-\s*(?P<date>\S+)", re.MULTILINE)


@dataclass
class ChangelogSection:
    version: str
    date: Optional[str]
    body_markdown: str


def parse_changelog(path: str) -> list[ChangelogSection]:
    """Parse `## [x.y.z] - date` sections (in file order = newest first)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    matches = list(_SECTION_RE.finditer(text))
    sections: list[ChangelogSection] = []
    for i, m in enumerate(matches):
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        sections.append(ChangelogSection(version=m.group("ver").strip(),
                                         date=m.group("date").strip(), body_markdown=body))
    return sections


def _to_dt(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def notes_since_last_stable_from_changelog(
    path: str, up_to_version: str
) -> tuple[list[ReleaseNoteItem], Optional[str]]:
    """Return CHANGELOG sections from `up_to_version` (inclusive) down to the next
    older section, as ReleaseNoteItems. Degraded fallback (stable-only)."""
    sections = parse_changelog(path)
    if not sections:
        return [], None
    target = parse_version(up_to_version)
    idx = next((i for i, s in enumerate(sections) if parse_version(s.version) == target), None)
    if idx is None:
        # Unknown current version (e.g. a pre-release not in CHANGELOG): show the newest section.
        idx = 0
    item = sections[idx]
    since = sections[idx + 1].version if idx + 1 < len(sections) else None
    return (
        [ReleaseNoteItem(version=item.version, date=_to_dt(item.date), is_prerelease=False,
                         url=None, body_markdown=item.body_markdown)],
        since,
    )
```

- [ ] **Step 4: Simplify the over-specified test**

Edit `test_changelog_fallback.py` `test_notes_for_current` to drop the speculative attribute line — replace its body with:

```python
def test_notes_for_current(tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(SAMPLE, encoding="utf-8")
    items, since = notes_since_last_stable_from_changelog(str(p), "1.36.0")
    assert items[0].version == "1.36.0"
    assert "thing A" in items[0].body_markdown
    assert since == "1.35.0"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_changelog_fallback.py -v --no-cov`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/update/changelog_fallback.py backend/tests/services/test_changelog_fallback.py
git commit -m "feat(updates): CHANGELOG.md offline fallback parser"
```

---

## Task 4: Rework ProdUpdateBackend (notes/check/releases via GitHub)

**Files:**
- Modify: `backend/app/services/update/prod_backend.py`
- Test: `backend/tests/services/test_update_github.py`

- [ ] **Step 1: Write the failing tests** (append to `test_update_github.py`)

```python
import pytest
from app.services.update.github_releases import GitHubRelease, GitHubUnavailable
from app.services.update.prod_backend import ProdUpdateBackend


def _gh(tag, pre, body="notes"):
    return GitHubRelease(tag=tag, name=tag, body_markdown=body, prerelease=pre, published_at=None, url=f"https://x/{tag}")


_REL = [_gh("v1.36.0", False), _gh("v1.35.1-pre.25", True), _gh("v1.35.0", False)]


class _FakeVersion:
    def __init__(self, v): self.version = v; self.commit = "c"; self.commit_short = "c"; self.tag = "v"+v; self.date = None


@pytest.mark.asyncio
async def test_get_release_notes_github(monkeypatch):
    b = ProdUpdateBackend()
    monkeypatch.setattr(b, "get_current_version", lambda: _FakeVersion("1.35.1-pre.25"))
    async def fake_list(*a, **k): return _REL
    monkeypatch.setattr(b._gh, "list_releases", fake_list)
    notes = await b.get_release_notes()
    assert notes.source == "github"
    assert [r.version for r in notes.releases] == ["1.35.1-pre.25"]  # since v1.35.0


@pytest.mark.asyncio
async def test_get_release_notes_falls_back_to_changelog(monkeypatch, tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("# Changelog\n\n## [1.36.0] - 2026-06-06\n\n### Added\n- a\n", encoding="utf-8")
    from app.core.config import settings
    monkeypatch.setattr(settings, "update_changelog_path", str(cl))
    b = ProdUpdateBackend()
    monkeypatch.setattr(b, "get_current_version", lambda: _FakeVersion("1.36.0"))
    async def boom(*a, **k): raise GitHubUnavailable("down")
    monkeypatch.setattr(b._gh, "list_releases", boom)
    notes = await b.get_release_notes()
    assert notes.source == "changelog"
    assert notes.releases[0].version == "1.36.0"


@pytest.mark.asyncio
async def test_check_for_updates_github(monkeypatch):
    b = ProdUpdateBackend()
    monkeypatch.setattr(b, "get_current_version", lambda: _FakeVersion("1.35.1-pre.25"))
    async def fake_list(*a, **k): return _REL
    monkeypatch.setattr(b._gh, "list_releases", fake_list)
    available, latest, changelog = await b.check_for_updates("stable")
    assert available is True and latest.version == "1.36.0"
    assert changelog and changelog[0].body_markdown == "notes"
```

Note: `get_current_version` is async in the real code — these tests stub it with a sync lambda returning an object; since the backend awaits it, replace the stub with an async one if a test errors. Use:

```python
    async def _ver(): return _FakeVersion("1.35.1-pre.25")
    monkeypatch.setattr(b, "get_current_version", _ver)
```

(Apply the async-stub form in all three tests.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_update_github.py -k "release_notes or check_for_updates" -v --no-cov`
Expected: FAIL — `ProdUpdateBackend` has no `_gh`; old `get_release_notes` returns `categories`.

- [ ] **Step 3: Rework prod_backend**

In `backend/app/services/update/prod_backend.py`:

(a) Extend the imports near the top:

```python
from app.core.config import settings
from app.schemas.update import ReleaseNoteItem
from app.services.update.github_releases import (
    GitHubReleasesClient, GitHubRelease, GitHubUnavailable,
    filter_channel, latest_for_channel, notes_since_last_stable, releases_between,
)
from app.services.update.changelog_fallback import notes_since_last_stable_from_changelog
```

(b) In `__init__`, add a client + a changelog-path resolver:

```python
        self._gh = GitHubReleasesClient()
```

And add this helper method to the class:

```python
    def _changelog_path(self) -> str:
        p = Path(settings.update_changelog_path)
        return str(p if p.is_absolute() else (self.repo_path / p))

    @staticmethod
    def _to_item(r: GitHubRelease) -> ReleaseNoteItem:
        from datetime import datetime
        date = None
        if r.published_at:
            try:
                date = datetime.fromisoformat(r.published_at.replace("Z", "+00:00"))
            except ValueError:
                date = None
        return ReleaseNoteItem(version=r.tag.lstrip("v"), date=date,
                               is_prerelease=r.prerelease, url=r.url, body_markdown=r.body_markdown)
```

(c) Replace `get_release_notes` entirely with:

```python
    async def get_release_notes(self) -> ReleaseNotesResponse:
        current = await self.get_current_version()
        try:
            releases = await self._gh.list_releases()
            slice_, since = notes_since_last_stable(releases, current.version)
            return ReleaseNotesResponse(
                current_version=current.version,
                since_version=since.lstrip("v") if since else None,
                source="github",
                releases=[self._to_item(r) for r in slice_],
            )
        except GitHubUnavailable:
            items, since = notes_since_last_stable_from_changelog(self._changelog_path(), current.version)
            return ReleaseNotesResponse(
                current_version=current.version,
                since_version=since.lstrip("v") if since else None,
                source="changelog",
                releases=items,
            )
```

(d) Replace `check_for_updates` and `_build_changelog` with a GitHub-driven version (delete the old
git-tag `check_for_updates` body and the `_build_changelog` method):

```python
    async def check_for_updates(self, channel: str) -> tuple[bool, Optional[VersionInfo], list[ChangelogEntry]]:
        current = await self.get_current_version()
        try:
            releases = await self._gh.list_releases()
        except GitHubUnavailable:
            return False, None, []

        latest = latest_for_channel(releases, channel)
        if latest is None:
            return False, None, []

        latest_v = parse_version(latest.tag)
        current_v = parse_version(current.version)
        if latest_v <= current_v:
            return False, None, []

        latest_info = VersionInfo(
            version=latest.tag.lstrip("v"), commit="", commit_short="",
            tag=latest.tag, date=None, is_prerelease=latest.prerelease,
        )
        delta = releases_between(releases, newer_than=current.version, up_to=latest.tag.lstrip("v"))
        changelog = [
            ChangelogEntry(version=r.tag.lstrip("v"), date=None, changes=[], breaking_changes=[],
                           is_prerelease=r.prerelease, body_markdown=r.body_markdown)
            for r in delta
        ]
        return True, latest_info, changelog
```

(e) Replace `get_all_releases` with a GitHub-driven version (delete the old git-tag body):

```python
    async def get_all_releases(self) -> ReleaseListResponse:
        try:
            releases = await self._gh.list_releases()
        except GitHubUnavailable:
            return ReleaseListResponse(releases=[], total=0)
        infos = [
            ReleaseInfo(
                tag=r.tag, version=r.tag.lstrip("v"), date=r.published_at,
                is_prerelease=r.prerelease, commit_short=None,
                name=r.name, html_url=r.url, body_markdown=r.body_markdown,
            )
            for r in releases
        ]
        return ReleaseListResponse(releases=infos, total=len(infos))
```

(f) Delete the `check_dev_branch` method from `prod_backend.py` entirely.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_update_github.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/update/prod_backend.py backend/tests/services/test_update_github.py
git commit -m "feat(updates): ProdUpdateBackend reads release-notes/check/releases from GitHub"
```

---

## Task 5: Rework DevUpdateBackend

**Files:**
- Modify: `backend/app/services/update/dev_backend.py`

- [ ] **Step 1: Replace `get_release_notes` with a markdown mock**

In `backend/app/services/update/dev_backend.py`, replace the `get_release_notes` method body with:

```python
    async def get_release_notes(self) -> ReleaseNotesResponse:
        from app.schemas.update import ReleaseNoteItem
        return ReleaseNotesResponse(
            current_version=version_to_string(self._simulated_version),
            since_version="0.9.0",
            source="github",
            releases=[
                ReleaseNoteItem(
                    version=version_to_string(self._simulated_version),
                    date=datetime.now(timezone.utc),
                    is_prerelease=False,
                    url="https://github.com/Xveyn/BaluHost/releases",
                    body_markdown="### Added\n- SSD cache management\n- SMB/WebDAV discovery\n\n### Fixed\n- Storage aggregation",
                ),
            ],
        )
```

Update the imports at the top of `dev_backend.py`: remove the now-unused `ReleaseNoteCategory`
import if present.

- [ ] **Step 2: Delete `check_dev_branch` from `dev_backend.py`** (if it overrides the base — remove the override).

- [ ] **Step 3: Run dev-mode smoke**

Run: `cd backend && python -c "import asyncio; from app.services.update.dev_backend import DevUpdateBackend; n=asyncio.run(DevUpdateBackend().get_release_notes()); print(n.source, n.releases[0].body_markdown[:10])"`
Expected: prints `github ### Added`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/update/dev_backend.py
git commit -m "feat(updates): DevUpdateBackend returns markdown release notes"
```

---

## Task 6: Remove dead development-branch logic

**Files:**
- Modify: `backend/app/services/update/backend.py`
- Modify: `backend/app/services/update/service.py`
- Modify: `backend/app/api/routes/updates.py`
- Test: `backend/tests/services/test_update_github.py`

- [ ] **Step 1: Write the failing test** (append)

```python
def test_dev_endpoints_and_fields_removed():
    import app.schemas.update as u
    assert not hasattr(u, "DevUpdateStartRequest")
    from app.api.routes import updates as r
    # No start-dev route registered
    paths = [getattr(rt, "path", "") for rt in r.router.routes]
    assert not any(p.endswith("/start-dev") for p in paths)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_update_github.py::test_dev_endpoints_and_fields_removed -v --no-cov`
Expected: FAIL (route + schema still present).

- [ ] **Step 3: Remove from the abstract interface**

In `backend/app/services/update/backend.py`, delete the `check_dev_branch` method (lines defining
`async def check_dev_branch...` through its `return False, None, None, []`). Remove the now-unused
`CommitInfo` import if nothing else in the file uses it.

- [ ] **Step 4: Drop dev_* from `service.check_for_updates` and remove `start_dev_update`**

In `backend/app/services/update/service.py`, in `check_for_updates`, delete the line:

```python
        dev_available, dev_version, dev_commits_ahead, dev_commits = await self.backend.check_dev_branch()
```

and remove the four `dev_*=...` keyword args from the `UpdateCheckResponse(...)` return.

Then delete the entire **`start_dev_update(...)`** method (the development-branch deploy path, ~lines
272-348) from the same file.

> **CAUTION — do NOT remove `_run_dev_update(...)`.** Despite the similar name, `_run_dev_update` is
> the shared **dev-mode in-process update simulator** that the normal `start_update` calls
> (`asyncio.create_task(self._run_dev_update(...))`). It must stay. Only `start_dev_update` (the
> development-*branch* method that calls `check_dev_branch`) is removed.

- [ ] **Step 5: Remove the route**

In `backend/app/api/routes/updates.py`, delete the entire `@router.post("/start-dev", ...)` handler
(`start_dev_update`) and drop `DevUpdateStartRequest` from the `from app.schemas.update import (...)`
import list.

- [ ] **Step 6: Run tests to verify they pass + no import errors**

Run: `cd backend && python -m pytest tests/services/test_update_github.py -v --no-cov && python -c "import app.api.routes.updates, app.services.update.service, app.services.update.backend"`
Expected: PASS; import line prints nothing (no error).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/update/backend.py backend/app/services/update/service.py backend/app/api/routes/updates.py backend/tests/services/test_update_github.py
git commit -m "refactor(updates): remove dead development-branch update path"
```

---

## Task 7: Final verification

- [ ] **Step 1: Run the new update tests**

Run: `cd backend && python -m pytest tests/services/test_github_releases.py tests/services/test_changelog_fallback.py tests/services/test_update_github.py -v --no-cov`
Expected: PASS (all).

- [ ] **Step 2: Run the existing update suite (no regression)**

Run: `cd backend && python -m pytest tests/services/test_update_service.py -q --no-cov`
Expected: PASS — or, for any test that asserted on the old git-tag `get_release_notes`/`check_for_updates`/`get_all_releases` or the removed `dev_*`/`start_dev_update`, update that test to the new contract (notes carry `releases[].body_markdown`; no `dev_*`). Document each changed test in the commit.

- [ ] **Step 3: Commit any test adjustments**

```bash
git add backend/tests/services/test_update_service.py
git commit -m "test(updates): adapt update-service tests to the GitHub-releases contract"
```

---

## Notes for the implementer

- **Positional, not semver-ordered:** all range logic uses the GitHub newest-first order; `parse_version` is only used for *equality* (finding a release by version) and the single `latest_v <= current_v` guard. Do not reintroduce semver sorting of `-pre.N`.
- **Public endpoint never 500s:** `get_release_notes` always returns a response (github or changelog). Keep the `try/except GitHubUnavailable` intact.
- **Out of scope:** `get_commit_history`/`get_commit_diff` stay git-based; `apply_updates`/`launch_update_script`/`rollback` unchanged.
- **Frontend is Plan 2:** API types, `react-markdown` rendering of `body_markdown`, removing the dev-channel UI, and i18n consume these contracts.
```
