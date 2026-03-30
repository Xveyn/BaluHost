# Docs-as-Manual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace build-time manual markdown articles with a backend API that serves the project's `docs/` directory as the single source of truth, with role-based visibility and i18n support.

**Architecture:** New backend service reads a `docs/manual-index.json` index file and serves markdown articles via two authenticated API endpoints. The frontend's static `import.meta.glob` loading is replaced with API hooks. Tabs are generated dynamically from the index. Admin-only doc groups are filtered server-side.

**Tech Stack:** Python/FastAPI (backend service + routes), Pydantic (schemas), React/TypeScript (frontend hooks + components), react-markdown (rendering, already installed), axios (API calls via existing `apiClient`)

**Spec:** `docs/superpowers/specs/2026-03-30-docs-as-manual-design.md`

---

## File Structure

### New Files
- `docs/manual-index.json` — Index defining groups, articles, visibility, i18n titles
- `backend/app/services/docs.py` — Service: load index, resolve articles, filter by role
- `backend/app/schemas/docs.py` — Pydantic models for API responses
- `backend/app/api/routes/docs.py` — Two endpoints: GET index, GET article
- `backend/tests/api/test_docs_routes.py` — API route tests
- `client/src/hooks/useDocsIndex.ts` — Hook: fetch doc groups from API
- `client/src/hooks/useDocsArticle.ts` — Hook: fetch single article content from API
- `client/src/components/manual/DocsGroupTab.tsx` — Generic tab component replacing SetupTab/WikiTab

### Modified Files
- `backend/app/api/routes/__init__.py` — Register docs router
- `backend/app/core/rate_limiter.py` — Add `docs_index` and `docs_article` rate limit keys
- `client/src/pages/UserManualPage.tsx` — Dynamic tabs from API, keep API Reference hardcoded
- `client/src/components/manual/ArticleCard.tsx` — Remove VersionBadge dependency
- `client/src/components/manual/ArticleView.tsx` — Remove VersionBadge, accept string content
- `client/src/i18n/locales/de/manual.json` — Update keys for dynamic tabs
- `client/src/i18n/locales/en/manual.json` — Update keys for dynamic tabs

### Deleted Files
- `client/src/content/manual/` — Entire directory (18 files)
- `client/src/hooks/useManualContent.ts` — Replaced by useDocsIndex + useDocsArticle
- `client/src/components/manual/SetupTab.tsx` — Replaced by DocsGroupTab
- `client/src/components/manual/WikiTab.tsx` — Replaced by DocsGroupTab
- `client/src/components/manual/VersionBadge.tsx` — No longer needed

### Renamed Files (docs/ migration)
- All markdown files listed in the index get `.de` suffix (e.g. `VPN_INTEGRATION.md` → `VPN_INTEGRATION.de.md`)
- English translations created as `.en.md` alongside each

---

## Task 1: Create `manual-index.json`

**Files:**
- Create: `docs/manual-index.json`

- [ ] **Step 1: Create the index file**

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
      "id": "api-docs",
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

- [ ] **Step 2: Commit**

```bash
git add docs/manual-index.json
git commit -m "feat(docs): add manual-index.json for docs-as-manual feature"
```

---

## Task 2: Rename existing docs with language suffix

**Files:**
- Rename: All markdown files referenced in `manual-index.json` get `.de` suffix

- [ ] **Step 1: Rename all referenced docs to add `.de` suffix**

Run this script from the project root. It reads the index, finds each file, and renames `FILENAME.md` → `FILENAME.de.md`:

```bash
cd "D:/Programme (x86)/Baluhost"

# getting-started
mv docs/getting-started/USER_GUIDE.md docs/getting-started/USER_GUIDE.de.md
mv docs/getting-started/DEV_CHECKLIST.md docs/getting-started/DEV_CHECKLIST.de.md

# network
mv docs/network/VPN_INTEGRATION.md docs/network/VPN_INTEGRATION.de.md
mv docs/network/WEBDAV_NETWORK_DRIVE.md docs/network/WEBDAV_NETWORK_DRIVE.de.md
mv docs/network/NETWORK_DRIVE_SETUP.md docs/network/NETWORK_DRIVE_SETUP.de.md
mv docs/network/NETWORK_DRIVE_QUICKSTART.md docs/network/NETWORK_DRIVE_QUICKSTART.de.md
mv docs/network/CLIENT_MDNS_SETUP.md docs/network/CLIENT_MDNS_SETUP.de.md
mv docs/network/FRITZBOX_WOL_PROTOCOL.md docs/network/FRITZBOX_WOL_PROTOCOL.de.md

# features
mv docs/features/SHARING_FEATURES_PHASE1.md docs/features/SHARING_FEATURES_PHASE1.de.md
mv docs/features/UPLOAD_PROGRESS.md docs/features/UPLOAD_PROGRESS.de.md
mv docs/features/USER_MANAGEMENT_FEATURES.md docs/features/USER_MANAGEMENT_FEATURES.de.md

# deployment
mv docs/deployment/DEPLOYMENT.md docs/deployment/DEPLOYMENT.de.md
mv docs/deployment/PRODUCTION_QUICKSTART.md docs/deployment/PRODUCTION_QUICKSTART.de.md
mv docs/deployment/PRODUCTION_READINESS.md docs/deployment/PRODUCTION_READINESS.de.md
mv docs/deployment/PRODUCTION_DEPLOYMENT_NOTES.md docs/deployment/PRODUCTION_DEPLOYMENT_NOTES.de.md
mv docs/deployment/FRONTEND_DEPLOYMENT.md docs/deployment/FRONTEND_DEPLOYMENT.de.md
mv docs/deployment/SSL_SETUP.md docs/deployment/SSL_SETUP.de.md
mv docs/deployment/REVERSE_PROXY_SETUP.md docs/deployment/REVERSE_PROXY_SETUP.de.md
mv docs/deployment/infrastructure.md docs/deployment/infrastructure.de.md
mv docs/deployment/emergency-runbook.md docs/deployment/emergency-runbook.de.md

# monitoring
mv docs/monitoring/MONITORING.md docs/monitoring/MONITORING.de.md
mv docs/monitoring/MONITORING_QUICKSTART.md docs/monitoring/MONITORING_QUICKSTART.de.md
mv docs/monitoring/DISK_IO_MONITOR.md docs/monitoring/DISK_IO_MONITOR.de.md
mv docs/monitoring/TELEMETRY_CONFIG_RECOMMENDATIONS.md docs/monitoring/TELEMETRY_CONFIG_RECOMMENDATIONS.de.md

# security
mv docs/security/SECURITY.md docs/security/SECURITY.de.md
mv docs/security/AUDIT_LOGGING.md docs/security/AUDIT_LOGGING.de.md
mv docs/security/API_RATE_LIMITING.md docs/security/API_RATE_LIMITING.de.md
mv docs/security/RATE_LIMITING_QUICKSTART.md docs/security/RATE_LIMITING_QUICKSTART.de.md
mv docs/security/SECURITY_AUDIT_2026-03-16.md docs/security/SECURITY_AUDIT_2026-03-16.de.md

# api
mv docs/api/API_REFERENCE.md docs/api/API_REFERENCE.de.md
```

- [ ] **Step 2: Update `docs/README.md` internal links**

Update any links in `docs/README.md` that point to renamed files — add `.de` before `.md` in each link that was renamed. Example: `USER_GUIDE.md` → `USER_GUIDE.de.md`.

- [ ] **Step 3: Create English placeholder files**

For each `.de.md` file, create a corresponding `.en.md` file. For now, copy the German content — proper translations will be done separately. Example:

```bash
# For each .de.md file, create a .en.md copy
for f in $(find docs -name "*.de.md" -not -path "docs/superpowers/*"); do
  en="${f%.de.md}.en.md"
  if [ ! -f "$en" ]; then
    cp "$f" "$en"
  fi
done
```

- [ ] **Step 4: Commit**

```bash
git add docs/
git commit -m "feat(docs): rename docs with .de suffix, create .en placeholders"
```

---

## Task 3: Backend Pydantic schemas

**Files:**
- Create: `backend/app/schemas/docs.py`

- [ ] **Step 1: Create the schemas file**

```python
"""Pydantic models for the documentation API."""

from pydantic import BaseModel


class DocsArticleInfo(BaseModel):
    """Article metadata as returned in the index."""
    slug: str
    title: str
    icon: str


class DocsGroupInfo(BaseModel):
    """Group of articles with label and icon."""
    id: str
    label: str
    icon: str
    articles: list[DocsArticleInfo]


class DocsIndexResponse(BaseModel):
    """Response for GET /api/docs/index."""
    groups: list[DocsGroupInfo]


class DocsArticleResponse(BaseModel):
    """Response for GET /api/docs/article/{slug}."""
    content: str
    title: str
    slug: str
    group: str
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/docs.py
git commit -m "feat(docs-api): add Pydantic schemas for docs endpoints"
```

---

## Task 4: Backend docs service

**Files:**
- Create: `backend/app/services/docs.py`

- [ ] **Step 1: Write the test file**

Create `backend/tests/api/test_docs_routes.py` with the service-level tests first:

```python
"""Tests for the documentation API endpoints."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.services.docs import DocsService


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------

class TestDocsService:
    """Unit tests for DocsService index loading and article resolution."""

    def _make_docs_dir(self, tmp_path: Path) -> Path:
        """Create a minimal docs directory with index and article files."""
        docs = tmp_path / "docs"
        docs.mkdir()

        # Create a simple index
        index = {
            "groups": [
                {
                    "id": "guides",
                    "labelDe": "Anleitungen",
                    "labelEn": "Guides",
                    "icon": "book",
                    "order": 1,
                    "visibility": "all",
                    "articles": [
                        {
                            "slug": "intro",
                            "path": "guides/INTRO",
                            "titleDe": "Einführung",
                            "titleEn": "Introduction",
                            "icon": "file-text",
                            "order": 1,
                        }
                    ],
                },
                {
                    "id": "admin-only",
                    "labelDe": "Admin",
                    "labelEn": "Admin",
                    "icon": "lock",
                    "order": 2,
                    "visibility": "admin",
                    "articles": [
                        {
                            "slug": "secrets",
                            "path": "admin/SECRETS",
                            "titleDe": "Geheimnisse",
                            "titleEn": "Secrets",
                            "icon": "key",
                            "order": 1,
                        }
                    ],
                },
            ]
        }
        (docs / "manual-index.json").write_text(json.dumps(index), encoding="utf-8")

        # Create article files
        guides = docs / "guides"
        guides.mkdir()
        (guides / "INTRO.de.md").write_text("# Einführung\n\nHallo Welt", encoding="utf-8")
        (guides / "INTRO.en.md").write_text("# Introduction\n\nHello World", encoding="utf-8")

        admin = docs / "admin"
        admin.mkdir()
        (admin / "SECRETS.de.md").write_text("# Geheimnisse\n\nNur für Admins", encoding="utf-8")

        return docs

    def test_load_index_returns_all_groups(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        index = svc.get_index(lang="de", is_admin=True)
        assert len(index) == 2
        assert index[0].id == "guides"
        assert index[1].id == "admin-only"

    def test_load_index_filters_admin_groups_for_regular_user(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        index = svc.get_index(lang="de", is_admin=False)
        assert len(index) == 1
        assert index[0].id == "guides"

    def test_get_index_resolves_german_labels(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        index = svc.get_index(lang="de", is_admin=False)
        assert index[0].label == "Anleitungen"
        assert index[0].articles[0].title == "Einführung"

    def test_get_index_resolves_english_labels(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        index = svc.get_index(lang="en", is_admin=False)
        assert index[0].label == "Guides"
        assert index[0].articles[0].title == "Introduction"

    def test_get_index_falls_back_to_de_for_unknown_lang(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        index = svc.get_index(lang="fr", is_admin=False)
        assert index[0].label == "Anleitungen"

    def test_get_article_returns_content(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        article = svc.get_article(slug="intro", lang="de", is_admin=False)
        assert article is not None
        assert "Einführung" in article.content
        assert article.slug == "intro"
        assert article.group == "guides"

    def test_get_article_returns_english_content(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        article = svc.get_article(slug="intro", lang="en", is_admin=False)
        assert article is not None
        assert "Hello World" in article.content

    def test_get_article_falls_back_to_de_when_lang_missing(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        # "secrets" only has .de.md, no .en.md
        article = svc.get_article(slug="secrets", lang="en", is_admin=True)
        assert article is not None
        assert "Nur für Admins" in article.content

    def test_get_article_returns_none_for_unknown_slug(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        article = svc.get_article(slug="nonexistent", lang="de", is_admin=False)
        assert article is None

    def test_get_article_returns_none_for_admin_slug_as_regular_user(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        article = svc.get_article(slug="secrets", lang="de", is_admin=False)
        assert article is None

    def test_rejects_path_traversal_in_index(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        bad_index = {
            "groups": [{
                "id": "evil",
                "labelDe": "Evil",
                "labelEn": "Evil",
                "icon": "x",
                "order": 1,
                "visibility": "all",
                "articles": [{
                    "slug": "evil",
                    "path": "../../../etc/passwd",
                    "titleDe": "Evil",
                    "titleEn": "Evil",
                    "icon": "x",
                    "order": 1,
                }],
            }]
        }
        (docs / "manual-index.json").write_text(json.dumps(bad_index), encoding="utf-8")
        svc = DocsService(docs_dir=docs)
        # Article with traversal path should be filtered out during index load
        index = svc.get_index(lang="de", is_admin=True)
        assert len(index[0].articles) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/api/test_docs_routes.py::TestDocsService -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.docs'`

- [ ] **Step 3: Implement the service**

Create `backend/app/services/docs.py`:

```python
"""Service for loading and serving project documentation as manual articles."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.schemas.docs import DocsArticleInfo, DocsArticleResponse, DocsGroupInfo

logger = logging.getLogger(__name__)

# Allowed language codes
_SUPPORTED_LANGS = {"de", "en"}
_FALLBACK_LANG = "de"


class DocsService:
    """Loads manual-index.json and serves markdown articles from the docs/ directory."""

    def __init__(self, docs_dir: Path | None = None) -> None:
        if docs_dir is None:
            # Default: project_root/docs (backend runs from backend/)
            docs_dir = Path(__file__).resolve().parent.parent.parent.parent / "docs"
        self._docs_dir = docs_dir
        self._index_path = self._docs_dir / "manual-index.json"
        self._cached_raw: dict | None = None
        self._cached_mtime: float = 0.0
        self._slug_map: dict[str, dict] = {}  # slug -> {path, group_id, group_visibility, titleDe, titleEn, icon}

    # ------------------------------------------------------------------
    # Index loading with mtime-based cache
    # ------------------------------------------------------------------

    def _load_index(self) -> dict:
        """Load and cache the index JSON, reloading if the file changed."""
        try:
            mtime = self._index_path.stat().st_mtime
        except FileNotFoundError:
            logger.warning("manual-index.json not found at %s", self._index_path)
            return {"groups": []}

        if self._cached_raw is not None and mtime == self._cached_mtime:
            return self._cached_raw

        raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        self._cached_raw = raw
        self._cached_mtime = mtime
        self._rebuild_slug_map(raw)
        return raw

    def _rebuild_slug_map(self, raw: dict) -> None:
        """Build a slug → metadata lookup, rejecting path-traversal entries."""
        slug_map: dict[str, dict] = {}
        for group in raw.get("groups", []):
            group_id = group.get("id", "")
            group_vis = group.get("visibility", "all")
            safe_articles = []
            for article in group.get("articles", []):
                path = article.get("path", "")
                # Reject path traversal
                if ".." in path.split("/"):
                    logger.warning("Rejected article with path traversal: %s", path)
                    continue
                slug = article.get("slug", "")
                if not slug:
                    continue
                slug_map[slug] = {
                    "path": path,
                    "group_id": group_id,
                    "group_visibility": group_vis,
                    "titleDe": article.get("titleDe", slug),
                    "titleEn": article.get("titleEn", slug),
                    "icon": article.get("icon", "file-text"),
                }
                safe_articles.append(article)
            group["articles"] = safe_articles
        self._slug_map = slug_map

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _resolve_lang(self, lang: str) -> str:
        """Normalize lang to a supported code, fallback to de."""
        code = lang.split("-")[0].lower() if lang else _FALLBACK_LANG
        return code if code in _SUPPORTED_LANGS else _FALLBACK_LANG

    def get_index(self, lang: str, is_admin: bool) -> list[DocsGroupInfo]:
        """Return the filtered, language-resolved index."""
        raw = self._load_index()
        resolved = self._resolve_lang(lang)

        label_key = f"label{'En' if resolved == 'en' else 'De'}"
        title_key = f"title{'En' if resolved == 'en' else 'De'}"

        groups: list[DocsGroupInfo] = []
        for g in sorted(raw.get("groups", []), key=lambda x: x.get("order", 99)):
            if g.get("visibility") == "admin" and not is_admin:
                continue
            articles = [
                DocsArticleInfo(
                    slug=a["slug"],
                    title=a.get(title_key, a.get("titleDe", a["slug"])),
                    icon=a.get("icon", "file-text"),
                )
                for a in sorted(g.get("articles", []), key=lambda x: x.get("order", 99))
            ]
            groups.append(DocsGroupInfo(
                id=g["id"],
                label=g.get(label_key, g.get("labelDe", g["id"])),
                icon=g.get("icon", "folder"),
                articles=articles,
            ))
        return groups

    def get_article(
        self, slug: str, lang: str, is_admin: bool
    ) -> Optional[DocsArticleResponse]:
        """Load a single article by slug. Returns None if not found or not authorized."""
        self._load_index()  # ensure slug_map is current
        meta = self._slug_map.get(slug)
        if meta is None:
            return None

        # Visibility check
        if meta["group_visibility"] == "admin" and not is_admin:
            return None

        resolved = self._resolve_lang(lang)
        title_key = f"title{'En' if resolved == 'en' else 'De'}"

        # Resolve file path with language fallback
        article_path = self._docs_dir / f"{meta['path']}.{resolved}.md"
        if not article_path.is_file() and resolved != _FALLBACK_LANG:
            article_path = self._docs_dir / f"{meta['path']}.{_FALLBACK_LANG}.md"

        if not article_path.is_file():
            logger.warning("Article file not found: %s", article_path)
            return None

        content = article_path.read_text(encoding="utf-8")
        return DocsArticleResponse(
            content=content,
            title=meta.get(title_key, meta.get("titleDe", slug)),
            slug=slug,
            group=meta["group_id"],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/api/test_docs_routes.py::TestDocsService -v
```

Expected: All 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/docs.py backend/tests/api/test_docs_routes.py
git commit -m "feat(docs-api): add DocsService with index loading and article resolution"
```

---

## Task 5: Backend API route + rate limits

**Files:**
- Create: `backend/app/api/routes/docs.py`
- Modify: `backend/app/api/routes/__init__.py`
- Modify: `backend/app/core/rate_limiter.py`

- [ ] **Step 1: Add route-level tests to the existing test file**

Append to `backend/tests/api/test_docs_routes.py`:

```python
# ---------------------------------------------------------------------------
# API route integration tests
# ---------------------------------------------------------------------------

@pytest.fixture
def _docs_dir_with_articles(tmp_path):
    """Create a temporary docs directory and patch DocsService to use it."""
    docs = tmp_path / "docs"
    docs.mkdir()

    index = {
        "groups": [
            {
                "id": "guides",
                "labelDe": "Anleitungen",
                "labelEn": "Guides",
                "icon": "book",
                "order": 1,
                "visibility": "all",
                "articles": [
                    {
                        "slug": "intro",
                        "path": "guides/INTRO",
                        "titleDe": "Einführung",
                        "titleEn": "Introduction",
                        "icon": "file-text",
                        "order": 1,
                    }
                ],
            },
            {
                "id": "admin-only",
                "labelDe": "Admin",
                "labelEn": "Admin",
                "icon": "lock",
                "order": 2,
                "visibility": "admin",
                "articles": [
                    {
                        "slug": "secrets",
                        "path": "admin/SECRETS",
                        "titleDe": "Geheimnisse",
                        "titleEn": "Secrets",
                        "icon": "key",
                        "order": 1,
                    }
                ],
            },
        ]
    }
    (docs / "manual-index.json").write_text(json.dumps(index), encoding="utf-8")

    guides = docs / "guides"
    guides.mkdir()
    (guides / "INTRO.de.md").write_text("# Einführung\n\nHallo", encoding="utf-8")
    (guides / "INTRO.en.md").write_text("# Introduction\n\nHello", encoding="utf-8")

    admin = docs / "admin"
    admin.mkdir()
    (admin / "SECRETS.de.md").write_text("# Secrets\n\nAdmin only", encoding="utf-8")

    with patch("app.api.routes.docs._get_docs_service") as mock:
        mock.return_value = DocsService(docs_dir=docs)
        yield


class TestDocsIndexEndpoint:
    """Integration tests for GET /api/docs/index."""

    def test_returns_index_for_admin(self, client, admin_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/index?lang=de", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["groups"]) == 2

    def test_filters_admin_groups_for_regular_user(self, client, user_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/index?lang=de", headers=user_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["groups"]) == 1
        assert data["groups"][0]["id"] == "guides"

    def test_resolves_english_labels(self, client, user_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/index?lang=en", headers=user_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["groups"][0]["label"] == "Guides"

    def test_requires_auth(self, client, _docs_dir_with_articles):
        resp = client.get("/api/docs/index")
        assert resp.status_code == 401


class TestDocsArticleEndpoint:
    """Integration tests for GET /api/docs/article/{slug}."""

    def test_returns_article_content(self, client, user_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/article/intro?lang=de", headers=user_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "Einführung" in data["content"]
        assert data["slug"] == "intro"
        assert data["group"] == "guides"

    def test_returns_english_article(self, client, user_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/article/intro?lang=en", headers=user_headers)
        assert resp.status_code == 200
        assert "Hello" in resp.json()["content"]

    def test_returns_404_for_unknown_slug(self, client, user_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/article/nonexistent?lang=de", headers=user_headers)
        assert resp.status_code == 404

    def test_returns_403_for_admin_article_as_regular_user(self, client, user_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/article/secrets?lang=de", headers=user_headers)
        assert resp.status_code == 403

    def test_admin_can_access_admin_article(self, client, admin_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/article/secrets?lang=de", headers=admin_headers)
        assert resp.status_code == 200
        assert "Admin only" in resp.json()["content"]

    def test_requires_auth(self, client, _docs_dir_with_articles):
        resp = client.get("/api/docs/article/intro")
        assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/api/test_docs_routes.py::TestDocsIndexEndpoint -v
cd backend && python -m pytest tests/api/test_docs_routes.py::TestDocsArticleEndpoint -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.routes.docs'`

- [ ] **Step 3: Add rate limit keys**

In `backend/app/core/rate_limiter.py`, add these two entries to the `RATE_LIMITS` dict, after the `"ad_discovery"` entry (around line 130):

```python
    # Documentation endpoints
    "docs_index": "60/minute",
    "docs_article": "120/minute",
```

- [ ] **Step 4: Create the route file**

Create `backend/app/api/routes/docs.py`:

```python
"""API routes for serving project documentation as a user manual."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api import deps
from app.core.rate_limiter import limiter, get_limit
from app.schemas.docs import DocsArticleResponse, DocsIndexResponse
from app.schemas.user import UserPublic
from app.services.docs import DocsService
from app.services.permissions import is_privileged

router = APIRouter(prefix="/docs", tags=["docs"])

# Module-level singleton; overridable in tests via _get_docs_service
_docs_service: DocsService | None = None


def _get_docs_service() -> DocsService:
    global _docs_service
    if _docs_service is None:
        _docs_service = DocsService()
    return _docs_service


@router.get("/index", response_model=DocsIndexResponse)
@limiter.limit(get_limit("docs_index"))
def get_docs_index(
    request: Request,
    response: Response,
    lang: str = "de",
    user: UserPublic = Depends(deps.get_current_user),
) -> DocsIndexResponse:
    """Return the documentation index, filtered by user role."""
    svc = _get_docs_service()
    groups = svc.get_index(lang=lang, is_admin=is_privileged(user))
    return DocsIndexResponse(groups=groups)


@router.get("/article/{slug}", response_model=DocsArticleResponse)
@limiter.limit(get_limit("docs_article"))
def get_docs_article(
    request: Request,
    response: Response,
    slug: str,
    lang: str = "de",
    user: UserPublic = Depends(deps.get_current_user),
) -> DocsArticleResponse:
    """Return a single documentation article by slug."""
    svc = _get_docs_service()
    admin = is_privileged(user)
    article = svc.get_article(slug=slug, lang=lang, is_admin=admin)

    if article is None:
        # Distinguish "not found" from "not authorized"
        # Check if slug exists at all (as admin) to return proper status
        exists = svc.get_article(slug=slug, lang=lang, is_admin=True)
        if exists is not None and not admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article '{slug}' not found",
        )
    return article
```

- [ ] **Step 5: Register the router**

In `backend/app/api/routes/__init__.py`, add the import and include:

Add to the import block (line 3-18):

```python
from app.api.routes import (
    auth, files, logging, system, users, upload_progress, shares, backup, sync,
    sync_advanced, mobile, vpn, health, admin_db, sync_compat, rate_limit_config,
    vcl, server_profiles, vpn_profiles, metrics, energy, devices, monitoring,
    power, power_presets, fans, service_status, schedulers, plugins, benchmark,
    notifications, updates, chunked_upload, webdav, samba, cloud, cloud_export,
    sleep,
    api_keys, desktop_pairing, ssd_file_cache, migration, pihole, env_config,
    backend_logs,
    activity,
    firebase_config,
    balupi,
    smart_devices,
    dashboard,
    fritzbox,
    docs,
)
```

Add after the last `include_router` line (after `dashboard.router`):

```python
api_router.include_router(docs.router, tags=["docs"])
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/api/test_docs_routes.py -v
```

Expected: All tests PASS (12 service tests + 9 route tests = 21 total).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/docs.py backend/app/api/routes/__init__.py backend/app/core/rate_limiter.py backend/tests/api/test_docs_routes.py
git commit -m "feat(docs-api): add /api/docs/index and /api/docs/article endpoints"
```

---

## Task 6: Frontend hooks

**Files:**
- Create: `client/src/hooks/useDocsIndex.ts`
- Create: `client/src/hooks/useDocsArticle.ts`

- [ ] **Step 1: Create `useDocsIndex.ts`**

```typescript
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../lib/api';

export interface DocsArticleInfo {
  slug: string;
  title: string;
  icon: string;
}

export interface DocsGroupInfo {
  id: string;
  label: string;
  icon: string;
  articles: DocsArticleInfo[];
}

export function useDocsIndex() {
  const { i18n } = useTranslation();
  const lang = i18n.language?.split('-')[0] ?? 'de';

  const [groups, setGroups] = useState<DocsGroupInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    apiClient
      .get<{ groups: DocsGroupInfo[] }>(`/api/docs/index`, { params: { lang } })
      .then((res) => {
        if (!cancelled) {
          setGroups(res.data.groups);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.response?.data?.detail ?? 'Failed to load documentation index');
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [lang]);

  return { groups, isLoading, error };
}
```

- [ ] **Step 2: Create `useDocsArticle.ts`**

```typescript
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../lib/api';

export interface DocsArticle {
  content: string;
  title: string;
  slug: string;
  group: string;
}

export function useDocsArticle(slug: string | null) {
  const { i18n } = useTranslation();
  const lang = i18n.language?.split('-')[0] ?? 'de';

  const [article, setArticle] = useState<DocsArticle | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) {
      setArticle(null);
      setIsLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    apiClient
      .get<DocsArticle>(`/api/docs/article/${slug}`, { params: { lang } })
      .then((res) => {
        if (!cancelled) {
          setArticle(res.data);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.response?.data?.detail ?? 'Failed to load article');
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [slug, lang]);

  return { article, isLoading, error };
}
```

- [ ] **Step 3: Commit**

```bash
git add client/src/hooks/useDocsIndex.ts client/src/hooks/useDocsArticle.ts
git commit -m "feat(frontend): add useDocsIndex and useDocsArticle hooks"
```

---

## Task 7: Frontend `DocsGroupTab` component

**Files:**
- Create: `client/src/components/manual/DocsGroupTab.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useTranslation } from 'react-i18next';
import { FileText, Loader2 } from 'lucide-react';
import type { DocsGroupInfo } from '../../hooks/useDocsIndex';
import { useDocsArticle } from '../../hooks/useDocsArticle';
import ArticleCard from './ArticleCard';
import ArticleView from './ArticleView';

interface DocsGroupTabProps {
  group: DocsGroupInfo;
  selectedArticle: string | null;
  onSelectArticle: (slug: string | null) => void;
}

export default function DocsGroupTab({ group, selectedArticle, onSelectArticle }: DocsGroupTabProps) {
  const { t } = useTranslation('manual');
  const { article, isLoading, error } = useDocsArticle(selectedArticle);

  if (selectedArticle) {
    if (isLoading) {
      return (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 text-cyan-400 animate-spin" />
        </div>
      );
    }
    if (error || !article) {
      return (
        <div className="flex flex-col items-center justify-center py-16 text-slate-500">
          <FileText className="h-12 w-12 mb-3 opacity-40" />
          <p className="text-sm">{error ?? t('errorLoading')}</p>
        </div>
      );
    }
    return (
      <ArticleView
        content={article.content}
        title={article.title}
        onBack={() => onSelectArticle(null)}
      />
    );
  }

  if (group.articles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500">
        <FileText className="h-12 w-12 mb-3 opacity-40" />
        <p className="text-sm">{t('noArticles')}</p>
      </div>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {group.articles.map((a) => (
        <ArticleCard
          key={a.slug}
          title={a.title}
          icon={a.icon}
          onClick={() => onSelectArticle(a.slug)}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/manual/DocsGroupTab.tsx
git commit -m "feat(frontend): add DocsGroupTab component"
```

---

## Task 8: Update `ArticleView` and `ArticleCard`

**Files:**
- Modify: `client/src/components/manual/ArticleView.tsx`
- Modify: `client/src/components/manual/ArticleCard.tsx`

- [ ] **Step 1: Rewrite `ArticleView.tsx`**

Remove the `Article` type dependency and `VersionBadge`. Accept `content`, `title`, and `onBack` props instead:

```typescript
import Markdown from 'react-markdown';
import { ArrowLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface ArticleViewProps {
  content: string;
  title: string;
  onBack: () => void;
}

export default function ArticleView({ content, title, onBack }: ArticleViewProps) {
  const { t } = useTranslation('manual');

  return (
    <div className="space-y-4">
      {/* Back button */}
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-sm text-slate-400 hover:text-cyan-400 transition-colors touch-manipulation"
        >
          <ArrowLeft className="h-4 w-4" />
          {t('backToOverview')}
        </button>
      </div>

      {/* Markdown content */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-slate-700/50 p-4 sm:p-6">
        <article className="prose prose-invert prose-slate max-w-none prose-headings:text-white prose-h1:text-xl prose-h1:sm:text-2xl prose-h1:font-bold prose-h2:text-lg prose-h2:sm:text-xl prose-h2:font-semibold prose-h2:mt-6 prose-h2:mb-3 prose-h3:text-base prose-h3:font-semibold prose-p:text-slate-300 prose-p:text-sm prose-p:sm:text-base prose-p:leading-relaxed prose-li:text-slate-300 prose-li:text-sm prose-li:sm:text-base prose-strong:text-white prose-code:text-cyan-400 prose-code:bg-slate-900/60 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:sm:text-sm prose-pre:bg-slate-900/60 prose-pre:border prose-pre:border-slate-700/50 prose-pre:rounded-lg prose-a:text-cyan-400 prose-a:no-underline hover:prose-a:underline">
          <Markdown>{content}</Markdown>
        </article>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Rewrite `ArticleCard.tsx`**

Remove the `Article` type and `VersionBadge` dependency. Accept `title`, `icon`, and `onClick` props:

```typescript
import * as Icons from 'lucide-react';

interface ArticleCardProps {
  title: string;
  icon: string;
  onClick: () => void;
}

/** Resolve a lucide icon name (e.g. "cloud-download") to a component */
function getLucideIcon(name: string): React.ReactNode {
  const pascal = name
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const IconComponent = (Icons as Record<string, any>)[pascal];
  if (IconComponent) return <IconComponent className="h-5 w-5" />;
  return <Icons.FileText className="h-5 w-5" />;
}

export default function ArticleCard({ title, icon, onClick }: ArticleCardProps) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-slate-800/40 backdrop-blur-sm rounded-xl border border-slate-700/50 p-4 hover:border-slate-600/50 hover:bg-slate-800/60 transition-all group touch-manipulation active:scale-[0.99]"
    >
      <div className="flex items-start gap-3">
        <div className="p-2 bg-cyan-500/20 rounded-lg text-cyan-400 group-hover:bg-cyan-500/30 transition-colors flex-shrink-0">
          {getLucideIcon(icon)}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm sm:text-base font-semibold text-white truncate">
            {title}
          </h3>
        </div>
        <Icons.ChevronRight className="h-5 w-5 text-slate-500 group-hover:text-slate-300 transition-colors flex-shrink-0 mt-0.5" />
      </div>
    </button>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add client/src/components/manual/ArticleView.tsx client/src/components/manual/ArticleCard.tsx
git commit -m "refactor(frontend): simplify ArticleView and ArticleCard props"
```

---

## Task 9: Update `UserManualPage.tsx`

**Files:**
- Modify: `client/src/pages/UserManualPage.tsx`

- [ ] **Step 1: Rewrite the page with dynamic tabs**

```typescript
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { BookOpen, Code, Loader2 } from 'lucide-react';
import * as Icons from 'lucide-react';
import { useVersion } from '../contexts/VersionContext';
import { useAuth } from '../contexts/AuthContext';
import { useDocsIndex } from '../hooks/useDocsIndex';
import DocsGroupTab from '../components/manual/DocsGroupTab';
import { ApiReferenceTab } from '../components/manual/ApiReferenceTab';

const API_REF_TAB_ID = '__api-reference__';

/** Resolve a lucide icon name to a component (for tab icons) */
function getTabIcon(name: string): React.ReactNode {
  const pascal = name
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const IconComp = (Icons as Record<string, any>)[pascal];
  if (IconComp) return <IconComp className="h-4 w-4" />;
  return <Icons.FileText className="h-4 w-4" />;
}

export default function UserManualPage() {
  const { t } = useTranslation(['manual', 'system', 'common']);
  const { version } = useVersion();
  const { token, isAdmin } = useAuth();
  const { groups, isLoading, error } = useDocsIndex();
  const [searchParams, setSearchParams] = useSearchParams();

  const rawTab = searchParams.get('tab') || '';
  const selectedArticle = searchParams.get('article') || null;

  // Determine active tab: first matching group id, or first available
  const validTabIds = new Set(groups.map((g) => g.id));
  if (isAdmin) validTabIds.add(API_REF_TAB_ID);
  const activeTab = validTabIds.has(rawTab) ? rawTab : (groups[0]?.id ?? '');

  const handleTabChange = (tab: string) => {
    setSearchParams({ tab });
  };

  const handleSelectArticle = (slug: string | null) => {
    if (slug) {
      setSearchParams({ tab: activeTab, article: slug });
    } else {
      setSearchParams({ tab: activeTab });
    }
  };

  return (
    <div className="space-y-4 sm:space-y-6 p-4 sm:p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold bg-gradient-to-r from-cyan-400 via-blue-400 to-violet-400 bg-clip-text text-transparent flex items-center gap-2 sm:gap-3">
            <BookOpen className="w-6 h-6 sm:w-8 sm:h-8 text-cyan-400" />
            {t('manual:title')}
          </h1>
          <p className="text-slate-400 text-xs sm:text-sm mt-1">
            {t('manual:version', { version: version ?? '...' })}
          </p>
        </div>
        {version && (
          <span className="self-start sm:self-center inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
            v{version}
          </span>
        )}
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 text-cyan-400 animate-spin" />
        </div>
      )}

      {/* Error state */}
      {error && !isLoading && (
        <div className="text-center py-16 text-red-400 text-sm">{error}</div>
      )}

      {/* Tab Navigation + Content */}
      {!isLoading && !error && (
        <>
          <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
            <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
              {groups.map((group) => (
                <button
                  key={group.id}
                  onClick={() => handleTabChange(group.id)}
                  className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                    activeTab === group.id
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                      : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
                  }`}
                >
                  {getTabIcon(group.icon)}
                  <span>{group.label}</span>
                </button>
              ))}
              {/* Hardcoded API Reference tab (admin only) */}
              {isAdmin && (
                <button
                  onClick={() => handleTabChange(API_REF_TAB_ID)}
                  className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                    activeTab === API_REF_TAB_ID
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                      : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
                  }`}
                >
                  <Code className="h-4 w-4" />
                  <span>{t('manual:tabs.api')}</span>
                </button>
              )}
            </div>
          </div>

          {/* Tab Content */}
          {activeTab === API_REF_TAB_ID && isAdmin ? (
            <ApiReferenceTab isAdmin={isAdmin} token={token} />
          ) : (
            (() => {
              const activeGroup = groups.find((g) => g.id === activeTab);
              return activeGroup ? (
                <DocsGroupTab
                  group={activeGroup}
                  selectedArticle={selectedArticle}
                  onSelectArticle={handleSelectArticle}
                />
              ) : null;
            })()
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/pages/UserManualPage.tsx
git commit -m "feat(frontend): dynamic manual tabs from docs API"
```

---

## Task 10: Update i18n and delete old files

**Files:**
- Modify: `client/src/i18n/locales/de/manual.json`
- Modify: `client/src/i18n/locales/en/manual.json`
- Delete: `client/src/content/manual/` (entire directory)
- Delete: `client/src/hooks/useManualContent.ts`
- Delete: `client/src/components/manual/SetupTab.tsx`
- Delete: `client/src/components/manual/WikiTab.tsx`
- Delete: `client/src/components/manual/VersionBadge.tsx`

- [ ] **Step 1: Update German i18n**

Replace `client/src/i18n/locales/de/manual.json`:

```json
{
  "title": "Benutzerhandbuch",
  "version": "Dokumentation für v{{version}}",
  "tabs": {
    "api": "API-Referenz"
  },
  "backToOverview": "Zurück zur Übersicht",
  "noArticles": "Noch keine Artikel vorhanden",
  "errorLoading": "Artikel konnte nicht geladen werden",
  "searchPlaceholder": "Artikel suchen..."
}
```

- [ ] **Step 2: Update English i18n**

Replace `client/src/i18n/locales/en/manual.json`:

```json
{
  "title": "User Manual",
  "version": "Documentation for v{{version}}",
  "tabs": {
    "api": "API Reference"
  },
  "backToOverview": "Back to overview",
  "noArticles": "No articles yet",
  "errorLoading": "Failed to load article",
  "searchPlaceholder": "Search articles..."
}
```

- [ ] **Step 3: Delete old files**

```bash
rm -rf client/src/content/manual/
rm client/src/hooks/useManualContent.ts
rm client/src/components/manual/SetupTab.tsx
rm client/src/components/manual/WikiTab.tsx
rm client/src/components/manual/VersionBadge.tsx
```

- [ ] **Step 4: Verify frontend builds**

```bash
cd client && npm run build
```

Expected: Build succeeds with no errors. (Warnings about unused imports are fine and should be resolved if any appear.)

- [ ] **Step 5: Commit**

```bash
git add -A client/src/i18n/locales/de/manual.json client/src/i18n/locales/en/manual.json
git rm -r client/src/content/manual/
git rm client/src/hooks/useManualContent.ts
git rm client/src/components/manual/SetupTab.tsx
git rm client/src/components/manual/WikiTab.tsx
git rm client/src/components/manual/VersionBadge.tsx
git commit -m "refactor(frontend): remove old manual content, update i18n for docs API"
```

---

## Task 11: Run all tests and verify

**Files:** None (verification only)

- [ ] **Step 1: Run backend tests**

```bash
cd backend && python -m pytest tests/api/test_docs_routes.py -v
```

Expected: All 21 tests pass.

- [ ] **Step 2: Run full backend test suite**

```bash
cd backend && python -m pytest --tb=short -q
```

Expected: No regressions. All existing tests still pass.

- [ ] **Step 3: Run frontend build**

```bash
cd client && npm run build
```

Expected: Clean build, no errors.

- [ ] **Step 4: Manual smoke test**

Start dev server (`python start_dev.py`), navigate to `/manual`:
- Verify tabs load dynamically from the index
- Verify clicking an article loads content from the API
- Verify admin-only tabs (Deployment, Monitoring, Security) only show for admin users
- Verify API Reference tab still works
- Verify language switch (de/en) updates tab labels and article content

- [ ] **Step 5: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address issues found during manual smoke test"
```
