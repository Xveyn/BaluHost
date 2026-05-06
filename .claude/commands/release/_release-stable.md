# Release Stable

Triggert den `release-stable.yml` Workflow auf GitHub. Promotet HEAD von `main` zu einem stabilen Release: Bump + CHANGELOG-Sektion + Stable-Tag + GitHub-Release als „Latest".

## Voraussetzung

- HEAD von `main` läuft auf der Production-NAS (Pre-Release wurde getestet)
- `gh` CLI ist authentifiziert

## Workflow

### 1. Bump-Type vorschlagen

Analysiere Commits seit letztem Stable-Tag:
```bash
LAST_STABLE=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | grep -Ev -- '-(pre|rc|alpha|beta|unstable)' | sort -V | tail -1)
git fetch origin main
git log "$LAST_STABLE"..origin/main --pretty=format:'%s'
```

**Vorschlag basierend auf Commits:**
- Mindestens ein `feat!:` oder `BREAKING CHANGE:` im Body → `major`
- Mindestens ein `feat:` → `minor`
- Sonst → `patch`

**FRAGE DEN BENUTZER:** Welcher Bump-Type? (Vorschlag anzeigen)

### 2. CHANGELOG-Vorschau lokal generieren

```bash
NEW_VERSION=$(python scripts/bump_version.py <bump_type> --dry-run | tail -1)
python scripts/generate_changelog_section.py \
  --version "$NEW_VERSION" \
  --since "$LAST_STABLE" \
  --output -
```

(Nur Vorschau — der echte CHANGELOG wird im Workflow geschrieben.)

**FRAGE DEN BENUTZER:** Sieht die Sektion korrekt aus?

### 3. Workflow triggern

**FRAGE DEN BENUTZER:** Trigger ausführen?

```bash
gh workflow run release-stable.yml --ref main -f bump_type=<type>
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
- NIEMALS in `CHANGELOG.md` lokal eine neue Sektion hinzufügen — der Workflow macht das
- Bei Workflow-Fehler: Run-Logs anzeigen und Benutzer informieren
