# Docs-as-Manual — Design Spec

**Date:** 2026-03-30
**Replaces:** Build-time manual content (`client/src/content/manual/`)
**Status:** Approved

---

## Overview

Replace the build-time markdown articles in `client/src/content/manual/` with a backend API that serves the existing `docs/` directory. The `docs/` files become the single source of truth for all user-facing documentation, served at runtime via authenticated endpoints with role-based visibility and i18n support.

## Goals

- **Single source of truth**: Documentation lives in `docs/`, not duplicated in the frontend bundle
- **Runtime delivery**: Docs can be updated on the server without a frontend rebuild
- **Role-based visibility**: Admin-only docs (deployment, monitoring, security) are filtered server-side
- **Bilingual**: All docs maintained in German (`.de.md`) and English (`.en.md`)

## Non-Goals

- Editing docs from the frontend (read-only)
- Full-text search across docs (future enhancement)
- Serving `superpowers/`, `plans/`, `CODE_ANALYSIS`, `sdk_plan.md`, `architecture-comparison.html`

---

## Docs File Structure

Existing docs are renamed with language suffixes. Files not in the manual index remain untouched.

```
docs/
├── manual-index.json
├── getting-started/
│   ├── USER_GUIDE.de.md
│   ├── USER_GUIDE.en.md
│   ├── DEV_CHECKLIST.de.md
│   └── DEV_CHECKLIST.en.md
├── network/
│   ├── VPN_INTEGRATION.de.md
│   ├── VPN_INTEGRATION.en.md
│   ├── WEBDAV_NETWORK_DRIVE.de.md
│   ├── WEBDAV_NETWORK_DRIVE.en.md
│   ├── NETWORK_DRIVE_SETUP.de.md
│   ├── NETWORK_DRIVE_SETUP.en.md
│   ├── NETWORK_DRIVE_QUICKSTART.de.md
│   ├── NETWORK_DRIVE_QUICKSTART.en.md
│   ├── CLIENT_MDNS_SETUP.de.md
│   ├── CLIENT_MDNS_SETUP.en.md
│   ├── FRITZBOX_WOL_PROTOCOL.de.md
│   └── FRITZBOX_WOL_PROTOCOL.en.md
├── features/
│   ├── SHARING_FEATURES_PHASE1.de.md
│   ├── SHARING_FEATURES_PHASE1.en.md
│   ├── UPLOAD_PROGRESS.de.md
│   ├── UPLOAD_PROGRESS.en.md
│   ├── USER_MANAGEMENT_FEATURES.de.md
│   └── USER_MANAGEMENT_FEATURES.en.md
├── deployment/                          (admin-only)
│   ├── DEPLOYMENT.de.md
│   ├── DEPLOYMENT.en.md
│   ├── PRODUCTION_QUICKSTART.de.md
│   ├── PRODUCTION_QUICKSTART.en.md
│   ├── PRODUCTION_READINESS.de.md
│   ├── PRODUCTION_READINESS.en.md
│   ├── PRODUCTION_DEPLOYMENT_NOTES.de.md
│   ├── PRODUCTION_DEPLOYMENT_NOTES.en.md
│   ├── FRONTEND_DEPLOYMENT.de.md
│   ├── FRONTEND_DEPLOYMENT.en.md
│   ├── SSL_SETUP.de.md
│   ├── SSL_SETUP.en.md
│   ├── REVERSE_PROXY_SETUP.de.md
│   ├── REVERSE_PROXY_SETUP.en.md
│   ├── infrastructure.de.md
│   ├── infrastructure.en.md
│   ├── emergency-runbook.de.md
│   └── emergency-runbook.en.md
├── monitoring/                          (admin-only)
│   ├── MONITORING.de.md
│   ├── MONITORING.en.md
│   ├── MONITORING_QUICKSTART.de.md
│   ├── MONITORING_QUICKSTART.en.md
│   ├── DISK_IO_MONITOR.de.md
│   ├── DISK_IO_MONITOR.en.md
│   ├── TELEMETRY_CONFIG_RECOMMENDATIONS.de.md
│   └── TELEMETRY_CONFIG_RECOMMENDATIONS.en.md
├── security/                            (admin-only)
│   ├── SECURITY.de.md
│   ├── SECURITY.en.md
│   ├── AUDIT_LOGGING.de.md
│   ├── AUDIT_LOGGING.en.md
│   ├── API_RATE_LIMITING.de.md
│   ├── API_RATE_LIMITING.en.md
│   ├── RATE_LIMITING_QUICKSTART.de.md
│   ├── RATE_LIMITING_QUICKSTART.en.md
│   ├── SECURITY_AUDIT_2026-03-16.de.md
│   └── SECURITY_AUDIT_2026-03-16.en.md
├── api/                                 (admin-only)
│   ├── API_REFERENCE.de.md
│   └── API_REFERENCE.en.md
│
│   # Untouched (not in manual index):
├── README.md
├── ARCHITECTURE.md
├── CODE_ANALYSIS_2026-03-17.md
├── TECHNICAL_DOCUMENTATION.md
├── architecture-comparison.html
├── sdk_plan.md
├── plans/
└── superpowers/
```

---

## Manual Index (`docs/manual-index.json`)

```json
{
  "groups": [
    {
      "id": "getting-started",
      "labelDe": "Erste Schritte",
      "labelEn": "Getting Started",
      "icon": "rocket",
      "order": 1,
      "visibility": "all",
      "articles": [
        {
          "slug": "user-guide",
          "path": "getting-started/USER_GUIDE",
          "titleDe": "Benutzerhandbuch",
          "titleEn": "User Guide",
          "icon": "book-open",
          "order": 1
        },
        {
          "slug": "dev-checklist",
          "path": "getting-started/DEV_CHECKLIST",
          "titleDe": "Entwickler-Checkliste",
          "titleEn": "Developer Checklist",
          "icon": "list-checks",
          "order": 2
        }
      ]
    },
    {
      "id": "setup",
      "labelDe": "Setup & Einrichtung",
      "labelEn": "Setup & Configuration",
      "icon": "wrench",
      "order": 2,
      "visibility": "all",
      "articles": [
        {
          "slug": "vpn",
          "path": "network/VPN_INTEGRATION",
          "titleDe": "VPN (WireGuard) einrichten",
          "titleEn": "VPN (WireGuard) Setup",
          "icon": "shield",
          "order": 1
        },
        {
          "slug": "webdav",
          "path": "network/WEBDAV_NETWORK_DRIVE",
          "titleDe": "WebDAV-Netzlaufwerk",
          "titleEn": "WebDAV Network Drive",
          "icon": "hard-drive",
          "order": 2
        },
        {
          "slug": "network-drive",
          "path": "network/NETWORK_DRIVE_SETUP",
          "titleDe": "Netzlaufwerk einrichten",
          "titleEn": "Network Drive Setup",
          "icon": "folder-sync",
          "order": 3
        },
        {
          "slug": "network-drive-quickstart",
          "path": "network/NETWORK_DRIVE_QUICKSTART",
          "titleDe": "Netzlaufwerk Schnellstart",
          "titleEn": "Network Drive Quickstart",
          "icon": "zap",
          "order": 4
        },
        {
          "slug": "mdns",
          "path": "network/CLIENT_MDNS_SETUP",
          "titleDe": "mDNS-Client einrichten",
          "titleEn": "mDNS Client Setup",
          "icon": "radio",
          "order": 5
        },
        {
          "slug": "fritzbox-wol",
          "path": "network/FRITZBOX_WOL_PROTOCOL",
          "titleDe": "Fritz!Box Wake-on-LAN",
          "titleEn": "Fritz!Box Wake-on-LAN",
          "icon": "power",
          "order": 6
        }
      ]
    },
    {
      "id": "features",
      "labelDe": "Features",
      "labelEn": "Features",
      "icon": "layers",
      "order": 3,
      "visibility": "all",
      "articles": [
        {
          "slug": "sharing",
          "path": "features/SHARING_FEATURES_PHASE1",
          "titleDe": "Dateifreigaben",
          "titleEn": "File Sharing",
          "icon": "share-2",
          "order": 1
        },
        {
          "slug": "upload-progress",
          "path": "features/UPLOAD_PROGRESS",
          "titleDe": "Upload-Fortschritt",
          "titleEn": "Upload Progress",
          "icon": "upload",
          "order": 2
        },
        {
          "slug": "user-management",
          "path": "features/USER_MANAGEMENT_FEATURES",
          "titleDe": "Benutzerverwaltung",
          "titleEn": "User Management",
          "icon": "users",
          "order": 3
        }
      ]
    },
    {
      "id": "deployment",
      "labelDe": "Deployment",
      "labelEn": "Deployment",
      "icon": "server",
      "order": 4,
      "visibility": "admin",
      "articles": [
        {
          "slug": "deployment",
          "path": "deployment/DEPLOYMENT",
          "titleDe": "Deployment-Guide",
          "titleEn": "Deployment Guide",
          "icon": "rocket",
          "order": 1
        },
        {
          "slug": "production-quickstart",
          "path": "deployment/PRODUCTION_QUICKSTART",
          "titleDe": "Produktion Schnellstart",
          "titleEn": "Production Quickstart",
          "icon": "zap",
          "order": 2
        },
        {
          "slug": "production-readiness",
          "path": "deployment/PRODUCTION_READINESS",
          "titleDe": "Produktionsreife-Checkliste",
          "titleEn": "Production Readiness Checklist",
          "icon": "clipboard-check",
          "order": 3
        },
        {
          "slug": "production-notes",
          "path": "deployment/PRODUCTION_DEPLOYMENT_NOTES",
          "titleDe": "Deployment-Notizen",
          "titleEn": "Deployment Notes",
          "icon": "file-text",
          "order": 4
        },
        {
          "slug": "frontend-deployment",
          "path": "deployment/FRONTEND_DEPLOYMENT",
          "titleDe": "Frontend-Deployment",
          "titleEn": "Frontend Deployment",
          "icon": "layout",
          "order": 5
        },
        {
          "slug": "ssl-setup",
          "path": "deployment/SSL_SETUP",
          "titleDe": "SSL/TLS-Konfiguration",
          "titleEn": "SSL/TLS Configuration",
          "icon": "lock",
          "order": 6
        },
        {
          "slug": "reverse-proxy",
          "path": "deployment/REVERSE_PROXY_SETUP",
          "titleDe": "Reverse-Proxy-Setup",
          "titleEn": "Reverse Proxy Setup",
          "icon": "arrow-right-left",
          "order": 7
        },
        {
          "slug": "infrastructure",
          "path": "deployment/infrastructure",
          "titleDe": "Infrastruktur",
          "titleEn": "Infrastructure",
          "icon": "network",
          "order": 8
        },
        {
          "slug": "emergency-runbook",
          "path": "deployment/emergency-runbook",
          "titleDe": "Notfall-Runbook",
          "titleEn": "Emergency Runbook",
          "icon": "alert-triangle",
          "order": 9
        }
      ]
    },
    {
      "id": "monitoring",
      "labelDe": "Monitoring",
      "labelEn": "Monitoring",
      "icon": "activity",
      "order": 5,
      "visibility": "admin",
      "articles": [
        {
          "slug": "monitoring",
          "path": "monitoring/MONITORING",
          "titleDe": "Monitoring-Setup",
          "titleEn": "Monitoring Setup",
          "icon": "bar-chart-3",
          "order": 1
        },
        {
          "slug": "monitoring-quickstart",
          "path": "monitoring/MONITORING_QUICKSTART",
          "titleDe": "Monitoring Schnellstart",
          "titleEn": "Monitoring Quickstart",
          "icon": "zap",
          "order": 2
        },
        {
          "slug": "disk-io",
          "path": "monitoring/DISK_IO_MONITOR",
          "titleDe": "Disk-I/O-Monitor",
          "titleEn": "Disk I/O Monitor",
          "icon": "hard-drive",
          "order": 3
        },
        {
          "slug": "telemetry-config",
          "path": "monitoring/TELEMETRY_CONFIG_RECOMMENDATIONS",
          "titleDe": "Telemetrie-Konfiguration",
          "titleEn": "Telemetry Configuration",
          "icon": "settings",
          "order": 4
        }
      ]
    },
    {
      "id": "security",
      "labelDe": "Sicherheit",
      "labelEn": "Security",
      "icon": "shield-check",
      "order": 6,
      "visibility": "admin",
      "articles": [
        {
          "slug": "security",
          "path": "security/SECURITY",
          "titleDe": "Sicherheitsübersicht",
          "titleEn": "Security Overview",
          "icon": "shield",
          "order": 1
        },
        {
          "slug": "audit-logging",
          "path": "security/AUDIT_LOGGING",
          "titleDe": "Audit-Logging",
          "titleEn": "Audit Logging",
          "icon": "scroll-text",
          "order": 2
        },
        {
          "slug": "rate-limiting",
          "path": "security/API_RATE_LIMITING",
          "titleDe": "API Rate Limiting",
          "titleEn": "API Rate Limiting",
          "icon": "gauge",
          "order": 3
        },
        {
          "slug": "rate-limiting-quickstart",
          "path": "security/RATE_LIMITING_QUICKSTART",
          "titleDe": "Rate Limiting Schnellreferenz",
          "titleEn": "Rate Limiting Quick Reference",
          "icon": "zap",
          "order": 4
        },
        {
          "slug": "security-audit",
          "path": "security/SECURITY_AUDIT_2026-03-16",
          "titleDe": "Security Audit (März 2026)",
          "titleEn": "Security Audit (March 2026)",
          "icon": "file-search",
          "order": 5
        }
      ]
    },
    {
      "id": "api",
      "labelDe": "API-Dokumentation",
      "labelEn": "API Documentation",
      "icon": "code",
      "order": 7,
      "visibility": "admin",
      "articles": [
        {
          "slug": "api-reference",
          "path": "api/API_REFERENCE",
          "titleDe": "API-Referenz",
          "titleEn": "API Reference",
          "icon": "file-code",
          "order": 1
        }
      ]
    }
  ]
}
```

**Key rules:**
- `path` is relative to `docs/`, without language suffix or `.md` extension
- Language suffix (`.de.md` / `.en.md`) is appended by the backend based on the `lang` query parameter
- `slug` must be unique across all groups (used for URL deep-linking)
- `visibility`: `"all"` (every authenticated user) or `"admin"` (privileged users only)
- Articles can reference files from any `docs/` subdirectory regardless of which group they belong to

---

## Backend API

### New file: `backend/app/api/routes/docs.py`

**Router prefix:** `/api/docs`

#### `GET /api/docs/index`

| Aspect | Detail |
|--------|--------|
| Auth | `Depends(get_current_user)` |
| Rate limit | `@limiter.limit(get_limit("docs_index"))` |
| Query params | `lang` (default: `"de"`, validated: `de` or `en`) |
| Response model | `DocsIndexResponse` (Pydantic) |

**Behavior:**
1. Load `manual-index.json` from disk (cached in-memory, reloaded on mtime change)
2. Filter groups: remove `visibility: "admin"` groups if user is not privileged
3. Map labels/titles to the requested language (`labelDe`/`labelEn` → `label`, `titleDe`/`titleEn` → `title`)
4. Return filtered, language-resolved index

**Response shape:**
```json
{
  "groups": [
    {
      "id": "setup",
      "label": "Setup & Einrichtung",
      "icon": "wrench",
      "articles": [
        { "slug": "vpn", "title": "VPN (WireGuard) einrichten", "icon": "shield" }
      ]
    }
  ]
}
```

#### `GET /api/docs/article/{slug}`

| Aspect | Detail |
|--------|--------|
| Auth | `Depends(get_current_user)` |
| Rate limit | `@limiter.limit(get_limit("docs_article"))` |
| Path param | `slug` (string) |
| Query params | `lang` (default: `"de"`, validated: `de` or `en`) |
| Response model | `DocsArticleResponse` (Pydantic) |

**Behavior:**
1. Look up `slug` in the cached index → find `path` and parent group
2. If slug not found → 404
3. If parent group is `visibility: "admin"` and user is not privileged → 403
4. Resolve file: `docs/{path}.{lang}.md`, fallback to `docs/{path}.de.md`
5. If file not found → 404
6. Read file content as UTF-8 string
7. Return content + metadata

**Response shape:**
```json
{
  "content": "# VPN (WireGuard) einrichten\n\nDiese Anleitung...",
  "title": "VPN (WireGuard) einrichten",
  "slug": "vpn",
  "group": "setup"
}
```

**Security:**
- No user-supplied file paths — slug is mapped to a path from the trusted index
- Path traversal impossible (index controls the mapping, `..` in index paths rejected at load time)
- Admin-only content filtered server-side before response

### New file: `backend/app/schemas/docs.py`

Pydantic models:
- `DocsArticleInfo` — `slug: str`, `title: str`, `icon: str`
- `DocsGroupInfo` — `id: str`, `label: str`, `icon: str`, `articles: list[DocsArticleInfo]`
- `DocsIndexResponse` — `groups: list[DocsGroupInfo]`
- `DocsArticleResponse` — `content: str`, `title: str`, `slug: str`, `group: str`

### New file: `backend/app/services/docs.py`

Service layer:
- `DocsService` class
- `_load_index()` — reads and caches `manual-index.json` with mtime check
- `get_index(lang, user)` — returns filtered groups
- `get_article(slug, lang, user)` — returns article content or raises
- Index path resolved relative to project root (`settings.base_dir / "docs" / "manual-index.json"`)

### Registration

- Add router to `backend/app/main.py` alongside existing routers
- Add rate limit keys `docs_index` and `docs_article` to rate limiter config

---

## Frontend Changes

### Deleted

- `client/src/content/manual/` — entire directory (18 files)
- `client/src/hooks/useManualContent.ts` — replaced by API hooks
- `client/src/components/manual/SetupTab.tsx` — replaced by `DocsGroupTab.tsx`
- `client/src/components/manual/WikiTab.tsx` — replaced by `DocsGroupTab.tsx`
- `client/src/components/manual/VersionBadge.tsx` — no longer needed (no per-article version in index)

### New: `client/src/hooks/useDocsIndex.ts`

- Fetches `GET /api/docs/index?lang={lang}`
- Returns `{ groups, isLoading, error }`
- Re-fetches on language change

### New: `client/src/hooks/useDocsArticle.ts`

- Fetches `GET /api/docs/article/{slug}?lang={lang}` on demand
- Returns `{ article, isLoading, error }`
- Called when user selects an article

### New: `client/src/components/manual/DocsGroupTab.tsx`

- Replaces `SetupTab.tsx` and `WikiTab.tsx`
- Generic component: receives `group` (from index) as prop
- Shows `ArticleCard` grid for the group's articles
- On card click → loads article via `useDocsArticle` → renders in `ArticleView`

### Modified: `client/src/pages/UserManualPage.tsx`

- Tab bar generated dynamically from `useDocsIndex().groups`
- Each group becomes a tab with its `label` and `icon`
- API Reference tab remains hardcoded as the last tab (only for admins, same condition as current)
- Deep-linking unchanged: `?tab={group.id}&article={slug}`

### Unchanged

- `client/src/components/manual/ArticleView.tsx` — renders markdown (receives content string as prop)
- `client/src/components/manual/ArticleCard.tsx` — card component
- `client/src/components/manual/ApiReferenceTab.tsx` — OpenAPI tab
- `client/src/i18n/locales/{de,en}/manual.json` — UI strings for the page shell (updated keys only)

---

## Migration Plan

### Docs files

1. Rename all docs files that are in the manual index: add `.de` suffix before `.md`
2. Create English translations (`.en.md`) for each renamed file
3. Files not in the index remain untouched

### Frontend content

1. Delete `client/src/content/manual/` entirely
2. The content from those files is superseded by the (much more detailed) `docs/` equivalents

### i18n

- `manual.json` namespace stays for UI strings (tab labels, back button, loading states, etc.)
- Remove keys that referenced the old article system (e.g. `staleness`, `noArticles`)
- Add keys for new states (e.g. `loadingArticle`, `errorLoading`)

---

## Security Checklist

- [x] Auth dependency on both endpoints (`get_current_user`)
- [x] Rate limiting on both endpoints
- [x] Pydantic response models (no raw dicts)
- [x] Slug-based lookup prevents path traversal
- [x] Admin-only groups filtered server-side
- [x] No user-supplied file paths reach `open()`
- [x] Index validated at load time (`..` in paths rejected)
