# Release Stable (Phase 2: Promote)

Promotet den bereits gemergten Release-Prep-PR (siehe `/release-prepare`) zu
einem Stable-Tag: verifiziert, dass `CHANGELOG.md` auf `main` eine
`## [Unreleased]`-Sektion enthält, triggert `release-stable.yml`, das die
Sektion finalisiert (`finalize_changelog_section.py`), die Version real
bumpt und taggt.

## Voraussetzung

- Der Release-Prep-PR aus `/release-prepare` ist gemerged (mit angepasster
  `chore: release vX.Y.Z`-Commit-Message)
- `gh` CLI ist authentifiziert

## Workflow

### 1. Zielversion abfragen

**FRAGE DEN BENUTZER:** Welche Version soll promotet werden? (z.B. `1.39.0` —
die in `/release-prepare` Schritt 2 berechnete Zielversion)

### 2. Verifizieren

```bash
git fetch origin main
git show origin/main:CHANGELOG.md | grep -c '^## \[Unreleased\]$'
```

Erwartet: `1`. Bei `0`: Release-Prep-PR wurde noch nicht gemerged — abbrechen,
Benutzer informieren. Bei `>1`: inkonsistenter Zustand — abbrechen, Benutzer
informieren (manuell prüfen).

### 3. Workflow triggern

**FRAGE DEN BENUTZER:** Trigger für Version `<version>` ausführen?

```bash
gh workflow run release-stable.yml --ref main -f version=<version>
```

### 4. Status-Link

```bash
sleep 3
gh run list --workflow=release-stable.yml --limit 1
```

Zeige dem Benutzer Run-URL.

## Regeln

- Workflow läuft auf `main`, nicht `development`
- NIEMALS lokal `pyproject.toml` / `package.json` / `CLAUDE.md` bumpen
- NIEMALS lokal Stable-Tags erstellen oder pushen
- Die CHANGELOG-Sektion wird in Phase 1 (`/release-prepare`) geschrieben, NICHT hier — dieser Schritt finalisiert nur die bereits vorhandene `## [Unreleased]`-Sektion
- Bei Workflow-Fehler: Run-Logs anzeigen und Benutzer informieren
