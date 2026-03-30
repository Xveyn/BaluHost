# User Manual Page — Design Spec

**Date:** 2026-03-29
**Replaces:** ApiCenterPage (API Center)
**Status:** Approved

---

## Overview

Replace the existing "API Center" page with a comprehensive "User Manual" page. The page serves as the central documentation hub within the BaluHost WebApp, covering setup guides, a knowledge base (wiki), and the existing API reference.

## Route & Navigation

- **Route:** `/manual`
- **Redirect:** `/docs` → `/manual` (backwards compatibility)
- **Nav entry in Layout.tsx:** replaces API Center at the same position
  - Label: `t('navigation.userManual')` / `t('navigation.userManualDesc')`
  - Icon: existing `navIcon.docs`
  - Path: `/manual`

## Page Structure

### Header
- Title: "User Manual" (i18n)
- Global version badge (right-aligned): `v1.20.5` from `VersionContext`
  - Version sourced from backend `/api/health` (tag for releases, commit for dev builds)

### Tabs (Query-Param `?tab=`)
1. **Setup** (`?tab=setup`) — default tab
2. **Wiki** (`?tab=wiki`)
3. **API Reference** (`?tab=api`)

### Deep-Links
- Tab selection: `?tab=setup`
- Article selection: `?tab=setup&article=cloud-import`
- Consistent with existing app pattern (e.g. `/system?tab=logs`, `/admin/system-control?tab=raid`)

## Markdown Content System

### File Structure
```
client/src/content/manual/
├── setup/
│   ├── cloud-import.de.md
│   ├── cloud-import.en.md
│   ├── vpn.de.md
│   ├── vpn.en.md
│   ├── mobile.de.md
│   ├── mobile.en.md
│   ├── desktop-sync.de.md
│   ├── desktop-sync.en.md
│   ├── pihole.de.md
│   ├── pihole.en.md
│   ├── smart-devices.de.md
│   ├── smart-devices.en.md
│   ├── notifications.de.md
│   ├── notifications.en.md
│   ├── samba.de.md
│   ├── samba.en.md
│   ├── webdav.de.md
│   └── webdav.en.md
└── wiki/
    └── (initially empty, articles added incrementally)
```

### Frontmatter Schema
```markdown
---
title: Cloud Import einrichten
slug: cloud-import
icon: cloud-download
version: 1.20.0
order: 1
---
```

| Field     | Type   | Description                                          |
|-----------|--------|------------------------------------------------------|
| `title`   | string | Display name (already translated per-file)           |
| `slug`    | string | URL parameter for deep-linking (`?article=<slug>`)   |
| `icon`    | string | lucide-react icon name for the overview card         |
| `version` | string | Version when article was last verified               |
| `order`   | number | Sort order in overview                               |

### Build-Time Loading
- `import.meta.glob` loads all `.md` files at build time
- Frontmatter extracted via simple regex (avoids heavy `gray-matter` dependency)
- Markdown rendered at runtime via `react-markdown`
- Language selection: `useManualContent` hook reads `i18n.language`, loads matching `.{lang}.md` file, falls back to `de`

### Staleness Indicator
- If `article.version < app.version`: amber badge "Zuletzt geprüft für v{article.version}"
- If `article.version >= app.version`: green badge (or no badge)

## Component Architecture

### New Files
```
client/src/pages/UserManualPage.tsx           — Main page (shell + tabs)
client/src/components/manual/
├── SetupTab.tsx                               — Setup article overview + article view
├── WikiTab.tsx                                — Wiki article overview + article view
├── ApiReferenceTab.tsx                        — Extracted from ApiCenterPage (OpenAPI + Rate Limits)
├── ArticleCard.tsx                            — Card for overview (icon, title, version badge)
├── ArticleView.tsx                            — Renders a markdown article
├── VersionBadge.tsx                           — Global + per-article version badge
└── useManualContent.ts                        — Hook: loads MD via import.meta.glob, parses frontmatter, filters by language
```

### Modified Files
- `ApiCenterPage.tsx` — deleted, replaced by `UserManualPage.tsx`
- `App.tsx` — route `/manual`, redirect `/docs` → `/manual`, lazy import `UserManualPage`
- `Layout.tsx` — nav label "User Manual", path `/manual`
- `i18n/index.ts` — new namespace `manual` (replaces `apiDocs`)
- `i18n/locales/de/manual.json` — German UI strings
- `i18n/locales/en/manual.json` — English UI strings
- `i18n/locales/{de,en}/common.json` — `navigation.userManual`, `navigation.userManualDesc`

### Deleted Files
- `i18n/locales/de/apiDocs.json` — replaced by `manual.json`
- `i18n/locales/en/apiDocs.json` — replaced by `manual.json`

## API Reference Tab

Extracts the full existing functionality from `ApiCenterPage.tsx`:

- OpenAPI schema loading via `useOpenApiSchema()`
- Category pills + sub-tabs for endpoint filtering
- Search field for endpoints
- `EndpointCard` component with rate-limit badges
- Base URL info box
- Admin toggle: API Docs vs. Rate Limits (`RateLimitsTab`)

Changes from current implementation:
- Header/title removed (provided by parent `UserManualPage`)
- User loading and rate-limit loading lifted to page level, passed as props
- Otherwise 1:1 feature parity

## i18n Strategy

### UI Strings — `manual` namespace
```json
{
  "title": "User Manual",
  "version": "Dokumentation für v{{version}}",
  "tabs": {
    "setup": "Setup",
    "wiki": "Wiki",
    "api": "API Reference"
  },
  "staleness": "Zuletzt geprüft für v{{version}}",
  "backToOverview": "Zurück zur Übersicht",
  "noArticles": "Noch keine Artikel vorhanden",
  "searchPlaceholder": "Artikel suchen..."
}
```

### Article Content
- NOT via i18n keys — separate `.de.md` / `.en.md` files per article
- `useManualContent` hook reads `i18n.language` and loads the matching file
- Fallback language: `de` (matches existing `fallbackLng` config)

### Navigation Keys (in `common.json`)
- `navigation.userManual` replaces `navigation.apiCenter`
- `navigation.userManualDesc` replaces `navigation.apiCenterDesc`

## Dependencies

### New
- `react-markdown` — render markdown to React components
- No `gray-matter` — frontmatter parsed via lightweight regex to keep bundle small

### Existing (reused)
- `useOpenApiSchema` hook
- `RateLimitsTab` component
- `EndpointCard` component
- `methodColors`, `ApiEndpoint` type from `data/api-endpoints`
- `VersionContext` / `useVersion`

## Setup Articles (Initial Content)

| Slug            | Topic                              |
|-----------------|------------------------------------|
| cloud-import    | OAuth/rclone configuration         |
| vpn             | WireGuard setup & client config    |
| mobile          | QR code pairing, app installation  |
| desktop-sync    | BaluDesk pairing                   |
| pihole          | Pi-hole DNS integration            |
| smart-devices   | Tapo smart plug connection         |
| notifications   | Firebase push setup                |
| samba           | SMB/Samba network shares           |
| webdav          | WebDAV server configuration        |

## Styling

Consistent with existing BaluHost WebApp:
- Tailwind CSS, slate/sky color scheme
- Glassmorphism cards (`bg-slate-800/40 backdrop-blur-sm border border-slate-700/50`)
- Tab styling matches SystemMonitor / SystemControlPage pattern
- Responsive (mobile hamburger menu, touch-friendly)
