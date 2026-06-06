# Update Page → GitHub Releases — Design Spec

**Date:** 2026-06-06
**Status:** Approved
**Author:** Sven (Xveyn) + Claude (via brainstorming session)
**Branch:** `feat/update-page-github-releases`

## Problem

The self-hosted update mechanism (`backend/app/services/update/`) derives "what's new" entirely
from **local git tags + commit subjects**: `get_release_notes()` shows the commits between the
current tag and the immediately-preceding tag, `check_for_updates()` finds the highest semver tag and
builds a changelog from raw commit messages, `get_all_releases()` lists git tags.

The release/deploy flow changed (2026-05): **every merge to `main` now creates a `v<x.y.z>-pre.<n>`
tag + a GitHub pre-release**, and stable releases are cut via `release-stable.yml`. Consequences:

- `get_release_notes()`'s "previous tag" is almost always the prior `…-pre.(n-1)`, so the notes shrink
  to a **single PR's commits** instead of meaningful "what changed since the last stable".
- The new flow generates **curated CHANGELOG sections + GitHub Release `body`s** (the real, readable
  notes), which the update page ignores in favour of raw commit subjects.
- `check_dev_branch()` / `start_dev_update()` query `origin/development`, but the `development` branch
  was **retired 2026-05-06** — dead code.
- Channel handling is inconsistent (`check` filters pre-releases, `release-notes` does not).

## Goal

Make **GitHub Releases** the single source for the update page's "Neuerungen", the "update available?"
check, and the releases list. The actual update (checkout/migrate/restart) stays git/systemd.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Scope | GitHub Releases becomes the source for **release-notes + check + releases list**; git only applies updates |
| "Neuerungen" content | **Since the last stable release** (rolls pre-release noise into one block) |
| Fallback (GitHub down / rate-limited) | Parse the bundled **`CHANGELOG.md`** |
| Dead `development` logic | **Remove** `start-dev` / `check_dev_branch` / `start_dev_update` + UI |
| Repo | Public (`Xveyn/BaluHost`) → GitHub API **without token**; cache against the 60/h rate limit |

## Architecture

```
GitHub Releases API  (GET /repos/{repo}/releases?per_page=100, public, no token)
        │  httpx (5s timeout, UA + Accept headers), per-worker in-memory TTL cache (~15 min)
        ▼
services/update/github_releases.py   (NEW)
  - list_releases()           -> [GitHubRelease{tag, name, body_md, prerelease, published_at, url}]
  - latest_for_channel(ch)    -> highest-semver release (stable: prerelease=false; unstable: any)
  - notes_since_last_stable(up_to)  -> [release bodies in (last_stable, up_to], newest first]
        │  on httpx error / 403 rate-limit / 4xx-5xx  →  CHANGELOG.md parser (NEW)
        ▼
ProdUpdateBackend (reworked)
  - get_release_notes()  -> notes since last stable, up to CURRENT          (source: github|changelog)
  - check_for_updates()  -> latest = latest_for_channel; changelog = notes (current, latest]
  - get_all_releases()   -> from GitHub releases (was git tags)
  - apply_updates/rollback/launch_update_script  -> UNCHANGED (git/systemd)
  - get_commit_history/get_commit_diff           -> UNCHANGED (git; dev Versions tab, out of scope)
  - check_dev_branch / start_dev_update          -> REMOVED
DevUpdateBackend -> mock returns GitHub-release-shaped markdown notes
```

**Core idea:** one source (GitHub Releases) for *display + availability*; git/systemd only *apply*.
The repo is configurable via a new setting so forks/tests can override it.

## Components

### New

| File | Purpose |
|---|---|
| `backend/app/services/update/github_releases.py` | httpx GitHub Releases client + TTL cache + `latest_for_channel` / `notes_since_last_stable` |
| `backend/app/services/update/changelog_fallback.py` | Parse bundled `CHANGELOG.md` → release-note items since last stable |
| `backend/tests/services/test_github_releases.py`, `test_changelog_fallback.py` | Unit tests (mocked httpx, no network) |

### Modified

| File | Change |
|---|---|
| `backend/app/services/update/prod_backend.py` | `get_release_notes`/`check_for_updates`/`get_all_releases` delegate to the GitHub client; remove `check_dev_branch` |
| `backend/app/services/update/dev_backend.py` | mock returns markdown notes (`body_markdown`); drop `check_dev_branch` |
| `backend/app/services/update/backend.py` | drop `check_dev_branch` from the abstract interface |
| `backend/app/services/update/service.py` | remove `start_dev_update` |
| `backend/app/api/routes/updates.py` | remove `POST /updates/start-dev` |
| `backend/app/schemas/update.py` | reshape `ReleaseNotesResponse`; add `body_markdown` to `ChangelogEntry`; extend `ReleaseInfo`; drop `DevUpdateStartRequest` |
| `backend/app/core/config.py` | `update_github_repo` (default `Xveyn/BaluHost`), `update_changelog_path` (default repo-root `CHANGELOG.md`) |
| `client/src/api/updates.ts` | mirror schema changes |
| `client/src/components/updates/*` | render `body_markdown` via `react-markdown`; `source` hint; remove dev-channel UI |
| `client/src/i18n/locales/{de,en}/updates.json` | `source.changelogFallback` (+ remove dev-channel strings) |

## Semantics

**Channel mapping:** `stable` → releases with `prerelease=false`; `unstable` → all releases.
**Latest available (check):** highest-semver release in the active channel (tag via existing `parse_version`).

**"Since last stable" — two distinct computations** (each aggregates the curated release `body`s,
newest first, one block per release with a version header):

| Display | Range |
|---|---|
| `/release-notes` (Neuerungen of the running version) | release bodies in **(last stable below `current`, `current`]** |
| `/check` changelog (what an update brings) | release bodies in **(`current`, `latest`]** |

## Schemas (`backend/app/schemas/update.py`)

```python
class ReleaseNoteItem(BaseModel):
    version: str
    date: datetime | None = None
    is_prerelease: bool = False
    url: str | None = None
    body_markdown: str = ""

class ReleaseNotesResponse(BaseModel):           # reshaped
    current_version: str
    since_version: str | None = None             # the last stable the notes start from
    source: Literal["github", "changelog"] = "github"
    releases: list[ReleaseNoteItem] = []

# ChangelogEntry: + body_markdown: str | None = None   (changes/breaking_changes kept, not populated here)
# ReleaseInfo:    + name: str | None, + html_url: str | None, + body_markdown: str | None ;
#                 commit_short becomes Optional (GitHub release has no short hash)
# DevUpdateStartRequest: removed
```

## Caching, Fallback & Errors

- **Cache:** per-worker in-memory TTL (~15 min) on the releases list. 4 workers × 4 windows/h ≈ ≤16
  calls/h — well under 60/h. (Deliberately no DB/SHM sharing — YAGNI.)
- **GitHub client:** `httpx` async, 5s timeout, headers `User-Agent: BaluHost` + `Accept:
  application/vnd.github+json`; one page `per_page=100`.
- **Fallback → `CHANGELOG.md`** on timeout / network error / HTTP 403 (rate limit) / 4xx-5xx: a small
  parser reads the `## [x.y.z] - date` sections and returns the section(s) since the last stable as
  markdown, `source="changelog"`. Degraded mode (CHANGELOG mainly has stable entries → a pre-release
  box shows the last stable section offline — better than empty).
- **Error invariants:**
  - `/release-notes` (public, no auth) **never 500s** — total failure → `releases=[]`,
    `source="changelog"`.
  - `/check` (admin) degrades the same way; never a hard error.
  - The `source` flag reaches the frontend so it can show a subtle "from CHANGELOG (offline)" note.

## Frontend

- `client/src/api/updates.ts` — mirror the schema changes (`ReleaseNoteItem`, reshaped
  `ReleaseNotesResponse`, `ChangelogEntry.body_markdown?`, extended `ReleaseInfo`).
- Release-notes display (`components/updates/`) — render each `release` block: version header + date +
  Pre-Release badge (exists) + `<Markdown>{body_markdown}</Markdown>` with the existing `prose`
  classes (same pattern as the manual `ArticleView`). Subtle "from CHANGELOG (offline)" hint when
  `source === 'changelog'`; optional link to `url`.
- Check changelog and releases list render `body_markdown` the same way (releases list collapsible +
  `html_url`).
- Remove the "Update from development" / dev-channel UI.
- `react-markdown` renders **no raw HTML** (no `rehype-raw`) → GitHub bodies are safe.

## Out of Scope

- The git/systemd **apply/rollback** path (`apply_updates`, `launch_update_script`, `run-update.sh`).
- `get_commit_history` / `get_commit_diff` (dev-only Versions tab; remain git-based).
- The release/deploy **workflows** themselves (already in their final form).

## Tests

**Backend:**
- `github_releases.py`: JSON→models; channel filter; `latest_for_channel`; `notes_since_last_stable`
  aggregation; TTL cache hit/miss; fallback to CHANGELOG on httpx error/403. httpx mocked
  (monkeypatch/`respx`) — no real network.
- `changelog_fallback.py`: extracts the section(s) since the last stable correctly.
- `prod_backend`: `get_release_notes` (since-last-stable up to current), `check_for_updates`
  (current→latest), `get_all_releases` against a mocked GitHub client.
- `dev_backend`: returns markdown notes; existing update tests stay green.

**Frontend:** Vitest — the release-notes component renders `body_markdown` (react-markdown) and shows
the `source==='changelog'` hint; types compile.

## Manual Smoke (dev + prod)

1. Dev: update page shows the mock markdown notes; no dev-channel button.
2. Prod (or against the public repo): release notes show the aggregated GitHub bodies **since the last
   stable**; `/check` shows the delta to latest for the active channel.
3. Simulate GitHub failure (block the host / force 403) → notes fall back to CHANGELOG with the
   "offline" hint; no 500.
4. Switch channel stable↔unstable → latest/available and the notes range adjust accordingly.

## Build Order

1. Config (`update_github_repo`, `update_changelog_path`) + schema reshape.
2. `github_releases.py` client + cache (TDD).
3. `changelog_fallback.py` parser (TDD).
4. Rework `prod_backend` (`get_release_notes`/`check_for_updates`/`get_all_releases`) + `dev_backend`.
5. Remove dead `development` logic (backend + route + schema).
6. Frontend: API types, markdown rendering, remove dev-channel UI, i18n.
7. Tests green (backend + frontend), smoke.
