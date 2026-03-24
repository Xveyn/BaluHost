# Ad Discovery — Design Spec

**Date**: 2026-03-24
**Status**: Draft
**Location**: New tab in Pi-hole page

## Overview

Feature to identify ad-serving domains that pass through Pi-hole unblocked. Combines heuristic pattern-matching with community blocklist cross-referencing. Allows manual review and on-the-fly creation of custom blocklists.

## Requirements

- **Heuristic detection**: Configurable pattern-matching (substring + regex) against permitted DNS queries
- **Community cross-reference**: Compare permitted domains against cached public blocklists the user hasn't subscribed to
- **Manual flagging**: Manually mark any domain as suspect
- **Blocking options**: Block via Pi-hole deny-list (single domain) or collect into named custom lists (adlist format)
- **Custom lists**: Named, exportable as `.txt`, deployable as Pi-hole adlist
- **Analysis modes**: Continuous background job (6h default) + manual on-demand
- **UI**: New tab "Ad Discovery" in existing Pi-hole page, matching existing style
- **Rock Pi note**: On the minimal BaluHost variant (SQLite, 4GB RAM), only on-demand analysis — no background job

## Data Model

### `ad_discovery_patterns`

Configurable heuristic rules for scoring domains.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer, PK | Auto-increment |
| pattern | String(253) | Substring or regex pattern |
| is_regex | Boolean | False = substring match, True = regex |
| weight | Float | Score weight 0.1–1.0, default 0.5 |
| category | String(50) | `ads`, `tracking`, `telemetry`, `analytics`, `fingerprinting` |
| is_default | Boolean | True = shipped with BaluHost, cannot be deleted (only disabled) |
| enabled | Boolean | Default True |

### `ad_discovery_reference_lists`

Community blocklists used for cross-referencing.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer, PK | Auto-increment |
| name | String(200) | Display name (e.g. "OISD Full") |
| url | String(2000) | Download URL |
| is_default | Boolean | Curated vs. user-added |
| enabled | Boolean | Whether active for matching |
| domain_count | Integer | Domain count after last fetch |
| last_fetched_at | DateTime, nullable | Last successful download |
| fetch_interval_hours | Integer | Refresh interval, default 24 |
| last_error | String, nullable | Last error message |
| last_error_at | DateTime, nullable | Last error timestamp |

Domain sets are NOT stored row-by-row in the DB. They are cached on disk as gzip-compressed files (`backend/data/ad_discovery_cache/{list_id}.gz`) and loaded into memory as `set[str]` for O(1) lookups.

### `ad_discovery_suspects`

Domains flagged as potentially ad-related.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer, PK | Auto-increment |
| domain | String(253), unique | The domain |
| first_seen_at | DateTime | First appearance in queries |
| last_seen_at | DateTime | Most recent query |
| query_count | Integer | Total times queried |
| heuristic_score | Float | Pattern-match score 0–1 |
| matched_patterns | JSON | List of pattern IDs/strings that matched |
| community_hits | Integer | Number of reference lists containing this domain |
| community_lists | JSON | Names of matching reference lists |
| source | String(20) | `heuristic`, `community`, `both`, `manual` |
| status | String(20) | `new`, `confirmed`, `dismissed`, `blocked` |
| resolved_at | DateTime, nullable | When status was changed from `new` |
| added_to_list_id | Integer, FK, nullable | References `ad_discovery_custom_lists.id` |

### `ad_discovery_custom_lists`

Named custom blocklists.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer, PK | Auto-increment |
| name | String(200), unique | List name |
| description | String(500) | Optional description |
| domain_count | Integer | Number of domains |
| created_at | DateTime | |
| updated_at | DateTime | |
| deployed | Boolean | Whether active as adlist in Pi-hole |
| adlist_url | String(500), nullable | Local URL when deployed |

### `ad_discovery_custom_list_domains`

Domains belonging to custom lists.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer, PK | Auto-increment |
| list_id | Integer, FK | References `ad_discovery_custom_lists.id`, ON DELETE CASCADE |
| domain | String(253) | |
| added_at | DateTime | |
| comment | String(500) | Optional |

Unique constraint on `(list_id, domain)`.

## Backend Architecture

### Module Structure

```
backend/app/services/pihole/ad_discovery/
├── __init__.py
├── scorer.py            — Heuristic pattern-matching engine
├── community_matcher.py — Reference list download, cache, matching
├── custom_lists.py      — Custom list CRUD + adlist file generation
├── analyzer.py          — Orchestrator combining scorer + matcher
└── background.py        — APScheduler background job
```

### `scorer.py` — Heuristic Engine

- Loads patterns from `ad_discovery_patterns` into memory (cached, refreshed on change)
- Compiles regex patterns once, reuses compiled objects
- `score_domain(domain: str) -> ScoredResult`: checks all active patterns, returns highest weight + list of matched patterns
- `score_domains(domains: list[str]) -> list[ScoredResult]`: batch method
- Substring match: case-insensitive `pattern in domain`
- Regex match: `re.search(compiled_pattern, domain)`

### `community_matcher.py` — Reference Lists

- `fetch_list(url: str) -> set[str]`: download, parse one-domain-per-line format (supports hosts-format, ignores comments/blanks)
- Disk cache: `backend/data/ad_discovery_cache/{list_id}.gz` (gzip)
- Memory: `dict[int, set[str]]` — all active lists as sets
- `refresh_all()`: refresh lists older than their `fetch_interval_hours`
- `match_domain(domain: str) -> MatchResult`: returns which lists contain the domain
- `match_domains(domains: list[str]) -> list[MatchResult]`: batch
- Memory footprint: ~50–100MB for 5–10 large lists (acceptable on NAS; Rock Pi would use fewer/smaller lists)

### `custom_lists.py` — Custom Lists

- CRUD for lists and their domains
- `generate_adlist_file(list_id: int) -> Path`: writes `.txt` in adlist format (one domain per line, header comment with list name + date)
- `deploy_to_pihole(list_id: int)`: serves file via static route, adds URL as adlist in Pi-hole, triggers gravity update
- `undeploy_from_pihole(list_id: int)`: removes adlist from Pi-hole, triggers gravity update
- `export_list(list_id: int) -> bytes`: returns `.txt` content for download
- Files stored in `backend/data/ad_discovery_lists/`

### `analyzer.py` — Orchestrator

- `analyze_queries(period: str, min_score: float) -> list[SuspectDomain]`:
  1. Query all FORWARDED/CACHED domains from `dns_queries` in period
  2. Aggregate unique domains with query count
  3. Filter out existing suspects with status `blocked` or `dismissed`
  4. Run scorer + community matcher
  5. Compute combined score
  6. Upsert into `ad_discovery_suspects`
  7. Return sorted list (highest score first)
- `add_manual_suspect(domain: str)`: add with source=`manual`, score=0
- `update_suspect_status(domain: str, status: str)`: change status, set `resolved_at`
- `block_suspect(domain: str, target: str, list_id: int | None)`:
  - `target="deny_list"`: call `pihole_backend.add_domain("deny", "exact", domain)`
  - `target="custom_list"`: add to specified custom list, regenerate adlist file if deployed

### `background.py` — Background Job

- Registered as APScheduler job (consistent with existing scheduler pattern)
- Default interval: 6 hours (configurable 1–24h)
- Watermark-based: tracks timestamp of last analyzed query
- Per run:
  1. Fetch FORWARDED/CACHED queries since watermark
  2. Aggregate unique domains with count
  3. Filter already-known suspects (blocked/dismissed)
  4. Score remaining domains
  5. Upsert suspects (new: insert; existing: update `query_count`, `last_seen_at`, recalculate scores)
  6. Update watermark

### Scoring Formula

```
combined_score = (W_h * heuristic_score) + (W_c * community_score)
```

- `W_h = 0.4`, `W_c = 0.6` (configurable)
- `heuristic_score`: highest weight among matched patterns (0–1), 0 if no match
- `community_score`: `min(1.0, community_hits / normalization_factor)` where `normalization_factor = max(3, active_lists * 0.5)`
- Minimum combined score for suspect insertion: **0.15** (configurable)

Score interpretation (UI color coding only, no automatic blocking):

| Combined Score | Assessment |
|----------------|-----------|
| 0.8–1.0 | Very likely ads/tracking |
| 0.5–0.8 | Probably suspicious |
| 0.15–0.5 | Possibly suspicious |

## API Endpoints

All under `/api/pihole/ad-discovery/`, admin-only (`Depends(get_current_admin)`), rate-limited.

### Analysis

| Method | Path | Description |
|--------|------|-------------|
| POST | `/analyze` | Start manual analysis. Body: `{ period: "24h"\|"7d"\|"30d", min_score: 0.15 }` |
| GET | `/suspects` | List suspects. Query: `status`, `source`, `sort_by`, `page`, `page_size` |
| PATCH | `/suspects/{domain}` | Change status: `confirmed`, `dismissed`, `blocked` |
| POST | `/suspects/manual` | Add domain manually. Body: `{ domain: str }` |
| POST | `/suspects/block` | Block domain. Body: `{ domain, target: "deny_list"\|"custom_list", list_id? }` |
| POST | `/suspects/bulk-action` | Bulk action. Body: `{ domains: list[str], action: "block"\|"dismiss"\|"confirm", target?, list_id? }` |

### Heuristic Patterns

| Method | Path | Description |
|--------|------|-------------|
| GET | `/patterns` | List all patterns |
| POST | `/patterns` | Add pattern. Body: `{ pattern, is_regex, weight, category }` |
| PATCH | `/patterns/{id}` | Update pattern (weight, enabled, category) |
| DELETE | `/patterns/{id}` | Delete user-defined pattern (defaults: disable only) |

### Reference Lists

| Method | Path | Description |
|--------|------|-------------|
| GET | `/reference-lists` | List all reference lists with cache status |
| POST | `/reference-lists` | Add reference list. Body: `{ name, url, fetch_interval_hours? }` |
| PATCH | `/reference-lists/{id}` | Update (enabled, fetch_interval_hours) |
| DELETE | `/reference-lists/{id}` | Delete user-defined list |
| POST | `/reference-lists/refresh` | Force refresh all enabled lists now |

### Custom Lists

| Method | Path | Description |
|--------|------|-------------|
| GET | `/custom-lists` | List all custom lists |
| POST | `/custom-lists` | Create list. Body: `{ name, description? }` |
| PATCH | `/custom-lists/{id}` | Update name/description |
| DELETE | `/custom-lists/{id}` | Delete list (undeploys from Pi-hole first) |
| GET | `/custom-lists/{id}/domains` | List domains in a list |
| POST | `/custom-lists/{id}/domains` | Add domain(s). Body: `{ domains: list[str], comment? }` |
| DELETE | `/custom-lists/{id}/domains/{domain}` | Remove domain from list |
| POST | `/custom-lists/{id}/deploy` | Deploy as adlist in Pi-hole + gravity update |
| POST | `/custom-lists/{id}/undeploy` | Remove from Pi-hole + gravity update |
| GET | `/custom-lists/{id}/export` | Download as `.txt` file |
| GET | `/custom-lists/{id}/adlist.txt` | Adlist file served for Pi-hole (no auth, accessed by Pi-hole) |

### Status & Config

| Method | Path | Description |
|--------|------|-------------|
| GET | `/status` | Dashboard data: suspect counts by status, last analysis timestamp, background job status |
| GET | `/config` | Current config (background interval, scoring weights, min score) |
| PATCH | `/config` | Update config |

## Frontend UI

New tab **"Ad Discovery"** in the existing Pi-hole page, matching existing page style.

### Header Area (always visible)

Status bar with key metrics:
- **New suspects**: count with status `new`
- **Last analysis**: timestamp + background job active/inactive badge
- **Reference lists**: X of Y active, last refresh time
- **Custom lists**: count, X deployed

"Start Analysis" button on the right.

### Main Area: Suspects Table

Sortable, filterable table of suspect domains:

| Domain | Score | Source | Queries | Community Hits | Status | Actions |
|--------|-------|--------|---------|----------------|--------|---------|
| `tracker.example.com` | 0.87 | both | 342 | 4/7 lists | new | Block / Dismiss |

- **Filters**: Status (new/confirmed/dismissed/blocked), Source (heuristic/community/both/manual), min-score slider
- **Sort**: Score, Query Count, Community Hits, Last Seen
- **Bulk actions**: Checkbox selection → "Block all" / "Dismiss all"
- **Block dialog**: On "Block" click → choose: direct deny-list OR add to custom list (dropdown with existing lists + "Create new list")
- **Score color coding**: 0.8+ red, 0.5–0.8 orange, 0.15–0.5 yellow

### Lower Area: Configuration Sub-Tabs

**Patterns tab**: Table of all heuristic rules. Defaults visually distinguished (only toggle on/off). User-defined can be edited/deleted. "Add Pattern" button. Shows: pattern string, type (substring/regex), weight, category, hit count.

**Reference Lists tab**: Card layout per list with name, URL, domain count, last fetch, status badge (current/stale/error). Toggle on/off. "Add List" button. "Refresh All" button.

**Custom Lists tab**: Card per list with name, domain count, deploy status badge (active in Pi-hole / not deployed). Actions: Open (shows domains), Deploy/Undeploy, Export .txt, Delete.

## Default Data

### Default Reference Lists (all disabled by default)

| Name | URL |
|------|-----|
| OISD Full | `https://big.oisd.nl/` |
| Hagezi Multi Pro | `https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/domains/pro.txt` |
| Steven Black Unified | `https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts` |
| EasyList Domains | `https://v.firebog.net/hosts/Easylist.txt` |
| AdGuard DNS Filter | `https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt` |

### Default Heuristic Patterns (~30-40 total)

**Category `ads`** (weight 0.7–0.9):
`ad.`, `ads.`, `adservice`, `adserver`, `doubleclick`, `googlesyndication`, `googleadservices`, `moatads`, `adnxs`, `adsrvr`

**Category `tracking`** (weight 0.5–0.8):
`tracker.`, `tracking.`, `pixel.`, `beacon.`, `collect.`, `telemetry.`, `clickstream`

**Category `analytics`** (weight 0.3–0.5):
`analytics.`, `metrics.`, `stats.`, `measure.`, `segment.io`, `hotjar`, `mouseflow`

**Category `fingerprinting`** (weight 0.6–0.8):
`fingerprint`, `browser-update`, `device-api`

Lower weights for `analytics` due to higher false-positive rate (e.g. `analytics.github.com` is legitimate).

## Resource Considerations

- Pattern matching runs entirely in memory (compiled regexes cached)
- Community sets loaded once, O(1) lookup per domain
- Typical background run with 10k new queries: <2 seconds
- No impact on DNS performance (reads from DB only, does not write to Pi-hole)
- Reference list cache on disk: 5–50MB depending on number of lists
- Memory for loaded sets: ~50–100MB for 5–10 large lists
- Rock Pi variant: on-demand only, fewer/smaller reference lists recommended
