# BaluHost Wiki — VitePress + Vercel

## Context
BaluHost hat 34+ Markdown-Docs im Repo, aber keine öffentliche Projektseite. Ziel: Eine zweisprachige (DE/EN) Wiki für Endnutzer, Admins und Entwickler — gehostet auf Vercel via VitePress. Separates Repo `BaluHost-Docs`.

---

## 1. Repo & VitePress Setup

**Neues Repo**: `BaluHost-Docs` auf GitHub

```
BaluHost-Docs/
├── docs/
│   ├── .vitepress/
│   │   ├── config/
│   │   │   ├── index.ts       # Merges locales
│   │   │   ├── shared.ts      # Logo, search, social links
│   │   │   ├── de.ts          # Nav + sidebar (Deutsch)
│   │   │   └── en.ts          # Nav + sidebar (English)
│   │   └── theme/
│   │       └── custom.css     # BaluHost Branding
│   ├── public/                # Logo, favicon, screenshots
│   ├── index.md               # DE Landing Page
│   ├── benutzer/              # DE Endnutzer-Docs
│   ├── admin/                 # DE Admin-Docs
│   ├── entwickler/            # DE Entwickler-Docs
│   └── en/                    # EN Mirror
│       ├── index.md
│       ├── user/
│       ├── admin/
│       └── developer/
├── package.json
├── vercel.json
└── .gitignore
```

**Key Config**:
- Deutsch = Root-Locale (kein Prefix), Englisch unter `/en/`
- Local search (built-in, mit DE/EN Übersetzungen)
- `cleanUrls: true` für schöne URLs

## 2. Seitenstruktur (MVP = 14 DE + 14 EN Seiten)

### Benutzer (benutzer/ | en/user/)
| Seite | Quelle |
|-------|--------|
| erste-schritte | `docs/getting-started/USER_GUIDE.md` |
| dateiverwaltung | Neu (aus TECHNICAL_DOCUMENTATION.md extrahieren) |
| freigaben | `docs/features/SHARING_FEATURES_PHASE1.md` |
| netzlaufwerk | `docs/network/NETWORK_DRIVE_QUICKSTART.md` + `WEBDAV_NETWORK_DRIVE.md` |
| vpn | `docs/network/VPN_INTEGRATION.md` (User-Teil) |
| faq | Neu |

### Admin (admin/ | en/admin/)
| Seite | Quelle |
|-------|--------|
| installation | `docs/deployment/PRODUCTION_QUICKSTART.md` + `DEPLOYMENT.md` |
| konfiguration | `docs/deployment/REVERSE_PROXY_SETUP.md` + `SSL_SETUP.md` |
| raid | `docs/storage/RAID_SETUP_WIZARD.md` + `RAID_SCRUB.md` |
| monitoring | `docs/monitoring/MONITORING.md` + `MONITORING_QUICKSTART.md` |

### Entwickler (entwickler/ | en/developer/)
| Seite | Quelle |
|-------|--------|
| architektur | `docs/ARCHITECTURE.md` (sanitized) |
| dev-setup | `docs/getting-started/DEV_CHECKLIST.md` + README |
| api-referenz | `docs/api/API_REFERENCE.md` (sanitized) |

### Landing Page
- Hero mit Feature-Übersicht, Tech Stack, Links zu BaluDesk/BaluApp
- Quelle: `README.md`

## 3. Vercel Deployment

```json
// vercel.json
{
  "buildCommand": "npm run docs:build",
  "outputDirectory": "docs/.vitepress/dist",
  "framework": "vitepress"
}
```

- Subdomain: `baluhost-docs.vercel.app`
- Auto-Deploy auf Push zu `main`
- PR Preview Deployments automatisch

## 4. Security — Nicht veröffentlichen

**Absolut ausschließen:**
- `.claude/rules/security-agent.md` (interne Security-Invarianten, Known Gaps)
- `.env` / `.env.production` Werte (nur Keys dokumentieren)
- Server-IPs, DB-Credentials, JWT-Secret-Details
- `_jail_path()` Implementierung, Token-Type-Check-Logik
- Rate-Limit-Werte pro Endpoint, Passwort-Blacklist
- `PRODUCTION_DEPLOYMENT_NOTES.md`, `PRODUCTION_READINESS.md`

**Sanitieren vor Veröffentlichung:**
- `ARCHITECTURE.md` — High-Level ok, Auth-Internals entfernen
- `API_REFERENCE.md` — Endpoints + Schemas ok, Auth-Implementierung entfernen
- `SECURITY.md` — "For Users" ok, "For Developers" entfernen

## 5. Umsetzungsreihenfolge

| Schritt | Was |
|---------|-----|
| 1 | Repo erstellen, `npm init`, VitePress installieren |
| 2 | Config-Struktur (shared.ts, de.ts, en.ts) + custom.css |
| 3 | Alle Placeholder-Seiten mit Frontmatter anlegen |
| 4 | Vercel verbinden, ersten Build deployen |
| 5 | Deutsche Inhalte migrieren (7 Hauptseiten aus bestehenden Docs) |
| 6 | Englische Übersetzungen (14 EN-Seiten) |
| 7 | Entwickler-Sektion schreiben (Architektur, API, Dev-Setup) |
| 8 | Landing Page gestalten |
| 9 | Security-Review aller Inhalte |
| 10 | Screenshots einfügen, polish, launch |

## 6. Verifizierung

- `npm run docs:dev` — Lokale Vorschau, alle Links prüfen
- `npm run docs:build` — Build muss fehlerfrei durchlaufen
- Locale-Switcher DE/EN testen
- Alle Sidebar-Links auf 404 prüfen
- Vercel Preview Deployment vor Merge zu main prüfen
- Security-Review: `grep` über alle .md Dateien nach Passwörtern, IPs, internen Pfaden
