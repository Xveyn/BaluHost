# Plan: Android-App und BaluDesk aus Monorepo extrahieren

## Context

BaluHost ist ein Monorepo mit Backend (Python), Frontend (TypeScript), Android-App (Kotlin) und Desktop-Client BaluDesk (C++/Electron). Die Android-App und BaluDesk haben keine Code-Abhängigkeiten zum Hauptprojekt (nur HTTP-API). Der Entwickler arbeitet per SSH am NAS (Backend/Frontend) und lokal am PC (BaluDesk/Android). Separate Repos ermöglichen saubere Trennung — jede Maschine klont nur das Nötige.

**Neue Repos (public):**
- `Xveyn/BaluDesk` — Desktop Sync Client
- `Xveyn/BaluApp` — Android App

**Git-History wird erhalten** via `git-filter-repo`.

---

## Phase 1: Vorbereitung

### 1.1 git-filter-repo installieren
```bash
pip install git-filter-repo
```

### 1.2 Zwei frische Klone erstellen (filter-repo arbeitet nur auf frischen Clones)
```bash
cd /tmp
git clone https://github.com/Xveyn/BaluHost.git BaluApp-extract
git clone https://github.com/Xveyn/BaluHost.git BaluDesk-extract
```

---

## Phase 2: Repos extrahieren (mit History)

### 2.1 BaluApp (Android) extrahieren
```bash
cd /tmp/BaluApp-extract
git filter-repo --path android-app/ --path-rename android-app/:
```
Ergebnis: Nur die 16 android-app Commits bleiben, Dateien liegen im Root.

### 2.2 BaluDesk extrahieren
```bash
cd /tmp/BaluDesk-extract
git filter-repo --path baludesk/ --path-rename baludesk/:
```
Ergebnis: Nur die 20 baludesk Commits bleiben, `backend/` und `frontend/` liegen im Root.

### 2.3 feat/BaluDesk Branch prüfen
Der Remote-Branch `origin/feat/BaluDesk` existiert. `git filter-repo` verarbeitet alle Branches automatisch — relevante Commits auf diesem Branch werden mit extrahiert. Nach der Extraktion prüfen ob der Branch noch sinnvoll ist.

---

## Phase 3: Neue GitHub-Repos erstellen und pushen

### 3.1 Repos auf GitHub erstellen
```bash
gh repo create Xveyn/BaluApp --public --description "BaluHost Android App" --source /tmp/BaluApp-extract --push
gh repo create Xveyn/BaluDesk --public --description "BaluHost Desktop Sync Client" --source /tmp/BaluDesk-extract --push
```

### 3.2 Verifizieren
- GitHub Web: Commit-History prüfen
- Dateistruktur im Root korrekt (keine verschachtelten Verzeichnisse)

---

## Phase 4: Hauptrepo aufräumen

### 4.1 Verzeichnisse entfernen
```bash
cd /home/sven/projects/BaluHost
git rm -r android-app/
git rm -r baludesk/
```

### 4.2 Referenzen aktualisieren

**`.gitattributes`** — 2 Zeilen entfernen:
```diff
-baludesk/ export-ignore
-android-app/ export-ignore
```

**`.gitignore`** — 2 Zeilen entfernen:
```diff
-baludesk/backend/build/
-baludesk/backend/build/**
```

**`CLAUDE.md`** (Zeile 14-15) — BaluDesk und Mobile Apps Einträge anpassen:
```diff
-- **BaluDesk**: Desktop sync client (C++ backend + Electron frontend), located in `baludesk/`
-- **Mobile Apps**: Native Android (Kotlin), iOS implementation guide available
+- **BaluDesk**: Desktop sync client → [Xveyn/BaluDesk](https://github.com/Xveyn/BaluDesk)
+- **BaluApp**: Android app → [Xveyn/BaluApp](https://github.com/Xveyn/BaluApp)
```

**`.claude/rules/architecture.md`** (Zeile 124-139) — Multi-Component Sektion aktualisieren:
```diff
 ## Multi-Component Architecture

-### BaluDesk (Desktop Sync Client)
-- C++ backend with Electron frontend
-- Located in `baludesk/`
-- Uses vcpkg for C++ dependencies
-- Communicates with backend API for sync operations
+### BaluDesk (Desktop Sync Client) — [Separate Repo](https://github.com/Xveyn/BaluDesk)
+- C++ backend with Electron frontend
+- Communicates with backend API for sync operations

-### TUI (Terminal UI)
-...
-
-### Mobile Apps
-- **Android**: Full native app in `android-app/` (175+ Kotlin files)
-- Both use QR code pairing with VPN config embedded
-- 30-day refresh tokens for mobile sessions
+### BaluApp (Android) — [Separate Repo](https://github.com/Xveyn/BaluApp)
+- Native Kotlin app
+- QR code pairing with VPN config embedded
+- 30-day refresh tokens for mobile sessions
```

**`.claude/commands/release.md`** (Zeile 87) — Hinweis auf excludierte Verzeichnisse entfernen/anpassen.

### 4.3 Nicht anfassen (kein Handlungsbedarf)
- `client/src/lib/secureStore.ts` — Die `baludesk-api-token` Keys sind nur localStorage-Strings. Umbenennen würde alle User ausloggen. Lassen wie es ist.
- `client/tests/e2e/` — Gleiche Keys, konsistent mit secureStore.ts.
- CI/CD Workflows — Referenzieren android-app/baludesk bereits nicht.

### 4.4 Commit
```bash
git add -A
git commit -m "chore: extract android-app and baludesk into separate repos

- Removed android-app/ → https://github.com/Xveyn/BaluApp
- Removed baludesk/ → https://github.com/Xveyn/BaluDesk
- Updated documentation references
- Cleaned up .gitattributes and .gitignore"
```

---

## Phase 5: Abschluss

### 5.1 Auf development pushen, dann nach main mergen
```bash
git push origin development
# PR erstellen oder direkt mergen je nach Workflow
```

### 5.2 Temporäre Klone aufräumen
```bash
rm -rf /tmp/BaluApp-extract /tmp/BaluDesk-extract
```

---

## Verifizierung

1. **BaluApp Repo**: `https://github.com/Xveyn/BaluApp` — Kotlin-Dateien im Root, 16 Commits
2. **BaluDesk Repo**: `https://github.com/Xveyn/BaluDesk` — `backend/` + `frontend/` im Root, 20 Commits
3. **BaluHost Repo**: Keine `android-app/` oder `baludesk/` Verzeichnisse mehr, alle Referenzen aktualisiert
4. `npm run build` im client/ — weiterhin erfolgreich (secureStore.ts unverändert)
5. `python -m pytest` im backend/ — weiterhin erfolgreich (keine Abhängigkeiten)

---

## Dateien die geändert werden

| Datei | Aktion |
|-------|--------|
| `android-app/` | Entfernt (ganzes Verzeichnis) |
| `baludesk/` | Entfernt (ganzes Verzeichnis) |
| `.gitattributes` | 2 Zeilen entfernen |
| `.gitignore` | 2 Zeilen entfernen |
| `CLAUDE.md` | Zeile 14-15 anpassen (Links zu neuen Repos) |
| `.claude/rules/architecture.md` | Multi-Component Sektion aktualisieren |
| `.claude/commands/release.md` | Zeile 87 anpassen |
