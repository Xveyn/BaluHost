
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Detailed rules are in `.claude/rules/` (automatically loaded by Claude Code).

## Codebase Search

Für Codebase-Suchen **immer** den `vectordb-search` MCP verwenden statt Grep/Glob/Agent-Explore:

- **Code suchen**: `mcp__vectordb-search__search_code` — semantische Suche nach Code-Snippets mit natürlicher Sprache
- **Dateien finden**: `mcp__vectordb-search__search_files` — Dateien nach Konzept/Feature finden
- **Symbole suchen**: `mcp__vectordb-search__search_symbols` — Funktionen, Klassen, Methoden nach Name oder Beschreibung
- **Index aktualisieren**: `mcp__vectordb-search__index_update` — nach größeren Änderungen inkrementell updaten
- **projectPath**: immer `D:/Programme (x86)/Baluhost`

Grep/Glob nur als Fallback verwenden, wenn vectordb-search keine passenden Ergebnisse liefert.

## GitHub Issues für Nebenbefunde

Wenn bei Code-Änderungen, Reviews oder Recherche ein **Nebenbefund** auftaucht, der **nicht** zum aktuellen Task gehört — z. B. ein pre-existing Bug, eine Altlast, ein Out-of-Scope-Verbesserungspunkt, ein latentes Risiko oder eine sinnvolle Folgearbeit — dann **nicht still weiterarbeiten und nicht heimlich mitfixen**, sondern:

1. Den Befund kurz benennen (Problem, Fundort `file:line`, warum out-of-scope).
2. **Fragen, ob ich dafür ein GitHub-Issue anlegen soll** (`gh issue create`), bevor ich es tue.
3. Bei Zustimmung: Issue mit klarem Titel, Problembeschreibung, Scope/Severity, Fundort und Fix-Vorschlag anlegen; passendes Label setzen; die Issue-Nummer zurückmelden.

Ziel: solche Punkte landen nachvollziehbar im Issue-Tracker statt nur in einer Chat-Notiz. Im Zweifel lieber fragen als übergehen. (Beispiel-Muster: Issue #157 — pre-existing Total-Aggregations-Quirk, beim Custom-Range-Feature bemerkt.)

## Project Overview

BaluHost is a full-stack self-hosted home server platform (NAS at its core) with multiple components:
- **Backend**: Python FastAPI (primary), located in `backend/`
- **Frontend**: React + TypeScript + Vite (Web UI), located in `client/`
- **TUI**: Terminal UI (Textual), located in `backend/baluhost_tui/`
- **BaluDesk**: Desktop sync client → [Xveyn/BaluDesk](https://github.com/Xveyn/BaluDesk)
- **BaluApp**: Android app → [Xveyn/BaluApp](https://github.com/Xveyn/BaluApp)

**Current Production Status**: ~99% production-ready, deployed in production (Jan 2026). PostgreSQL, security hardening, and deployment complete.

## Architecture

```
backend/
├── app/
│   ├── api/routes/        # API endpoints
│   ├── services/          # Business logic
│   ├── schemas/           # Pydantic models
│   ├── models/            # SQLAlchemy ORM models
│   └── core/config.py     # Configuration
├── baluhost_tui/          # Terminal UI application
├── tests/                 # Pytest tests (82 files, 1465 test functions)
└── pyproject.toml         # Dependencies

client/
├── src/
│   ├── pages/             # Page components
│   ├── components/        # Reusable components
│   ├── api/               # API client modules
│   ├── lib/api.ts         # Base API client (axios)
│   └── hooks/             # Custom React hooks
└── vite.config.ts
```

## Quick Reference: Finding Things

**Authentication logic**: `backend/app/services/auth.py` + `backend/app/api/deps.py`
**File upload handling**: `backend/app/services/files.py:upload_file()`
**RAID status**: `backend/app/services/hardware/raid/`
**Frontend API client**: `client/src/lib/api.ts`
**Dashboard page**: `client/src/pages/Dashboard.tsx`
**Database models**: `backend/app/models/`
**API schemas**: `backend/app/schemas/`
**Tests**: `backend/tests/`
**Fan control**: `backend/app/services/power/fan_control.py`
**Power management**: `backend/app/services/power/manager.py`
**Monitoring orchestrator**: `backend/app/services/monitoring/orchestrator.py`
**Service status**: `backend/app/services/service_status.py`
**Network discovery**: `backend/app/services/network_discovery.py`
**Scheduler service**: `backend/app/services/scheduler/service.py`
**Scheduler Dashboard**: `client/src/pages/SchedulerDashboard.tsx`
**Setup wizard**: `backend/app/services/setup/`, `backend/app/api/routes/setup.py`
**Marketplace index signing**: `backend/app/plugins/signing.py`, gate in `backend/app/services/plugin_marketplace.py:get_index()`

Each major directory has its own CLAUDE.md with structure, conventions, and patterns specific to that area. **Keep these in sync when adding/removing files or changing patterns.**

### Backend (`backend/app/`)
- `api/CLAUDE.md` — Routes, auth dependencies, endpoint conventions
- `compat/CLAUDE.md` — WebDAV bridge, asyncio patches
- `core/CLAUDE.md` — Config, DB, security, lifespan, rate limiting
- `middleware/CLAUDE.md` — All 8 middleware with purpose and scope
- `models/CLAUDE.md` — SQLAlchemy model groups, conventions
- `plugins/CLAUDE.md` — Plugin system architecture and lifecycle
- `schemas/CLAUDE.md` — Pydantic schema conventions
- `services/CLAUDE.md` — Service layer structure, dev/prod backends

### Frontend (`client/src/`)
- `api/CLAUDE.md` — API client modules, axios patterns
- `components/CLAUDE.md` — Component structure, ui/ primitives, feature dirs
- `contexts/CLAUDE.md` — React contexts, provider nesting
- `hooks/CLAUDE.md` — Custom hooks, data fetching patterns
- `i18n/CLAUDE.md` — i18next setup, namespaces, locale files
- `lib/CLAUDE.md` — Core utilities, feature flags, error handling
- `pages/CLAUDE.md` — Route pages, device modes, lazy loading
- `types/CLAUDE.md` — TypeScript types, ambient declarations

## Plugin Marketplace Signing — Trust Mechanic (fail-closed)

External (marketplace) plugins are the untrusted-code attack surface. Their
`index.json` is cryptographically anchored so a compromised/MITM'd index can't
become RCE. **Do not weaken or bypass any part of this chain.**

- **Detached ed25519 over the RAW index bytes.** `MarketplaceService.get_index()`
  fetches `index.json` + `index.json.sig` and verifies the signature over the
  *exact bytes* it will then `json.loads` (no re-fetch → no TOCTOU), **before**
  the index is parsed or trusted. Verify util: `app/plugins/signing.py`
  (`verify_detached_ed25519`). The cache stores only post-verification indexes.
- **Fail-closed, always.** An empty trusted-key list, a missing/unfetchable
  `.sig`, or an invalid signature **rejects** the index (`IndexSignatureError`).
  There is **no unsigned fallback** — never add one. Archive integrity stays
  transitive via the now-signed `checksum_sha256` (no installer change).
- **Trusted keys come from config, default empty.** `settings.plugins_marketplace_public_keys`
  (`config.py`). Empty default = the marketplace is rejected until a key is
  provisioned — that is intentional, not a bug. Env is **plain CSV**
  (`PLUGINS_MARKETPLACE_PUBLIC_KEYS=key1,key2`), parsed by a `mode="before"`
  comma-split validator mirroring `parse_privileged_roles` — **not** Pydantic's
  JSON default (base64 has no comma; avoids shell/systemd quote-stripping).
- **The signing PRIVATE key never enters this repo, a commit, or an AI session.**
  It lives on the maintainer's machine / as the `BaluHost-Plugin-Market` GitHub
  secret. Only the public key is provisioned, out-of-band, via
  `deploy/scripts/install-marketplace-pubkey.sh` (idempotent; validates each key
  decodes to 32 bytes). Rotation = append more keys to the CSV.
- **Deploy verifies, never blocks.** `python -m app.plugins.verify_index_signature`
  runs as a non-fatal smoke-check in `deploy/scripts/ci-deploy.sh` (always exits 0;
  prints PASS/WARN).
- **Route error mapping:** `IndexSignatureError` → `BadGatewayError` (a
  `ServiceError`, 502) so the curated detail survives the global 5xx scrubber —
  a plain `HTTPException(502)` would be rewritten to "Internal server error".

Provisioning on a fresh box (companion-repo signing setup + `install-marketplace-pubkey.sh`)
is a one-time operator step needed before the first signed index; until then the
marketplace is fail-closed (harmless — 0 external plugins deployed). Design detail:
`docs/superpowers/specs/2026-06-28-plugin-marketplace-index-signing-design.md`.

## Contact & Support

- **Issues**: GitHub Issues (repository URL needed)
- **Documentation**: See `docs/` directory
- **Maintainer**: Xveyn
- **Version**: 1.37.0 (as of May 2026)
