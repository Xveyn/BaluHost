# Release: development → main (via PR + Label)

Erstelle einen Release-PR von development nach main. Die Versionsnummer wird automatisch im CI/CD-Workflow aus dem GitHub-Label bestimmt und gebumpt.

## Workflow

### 1. Status prüfen

Prüfe ob wir auf dem `development` Branch sind:
```bash
git branch --show-current
```

Falls nicht auf `development`: Abbrechen mit Hinweis.

Zeige Commits seit dem letzten Tag auf main:
```bash
git log $(git describe --tags --abbrev=0 main 2>/dev/null || echo "main")..HEAD --oneline
```

### 2. Release-Typ bestimmen

**ZEIGE DEM BENUTZER** die aktuelle Version und die Änderungen:
```bash
python scripts/bump_version.py  # Zeigt aktuelle Version (sync-only)
```

**FRAGE DEN BENUTZER:** Welcher Release-Typ?
- `patch` (x.x.X) — Bugfixes
- `minor` (x.X.0) — Neue Features
- `major` (X.0.0) — Breaking Changes

Schlage basierend auf den Commits vor:
- Nur `fix:` Commits → `patch`
- Mindestens ein `feat:` Commit → `minor`
- Breaking Changes (z.B. `feat!:`, `BREAKING CHANGE`) → `major`

### 3. CHANGELOG aktualisieren

Erstelle einen CHANGELOG-Eintrag nach Keep a Changelog Format:
- Gruppiere nach: Added, Changed, Fixed, Removed
- Extrahiere Informationen aus den Commit-Messages
- Verwende Conventional Commits Präfixe (feat, fix, refactor, docs, chore)

**FRAGE DEN BENUTZER:** Ist der CHANGELOG-Eintrag korrekt?

### 4. Commit + Push

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for next release"
git push origin development
```

**FRAGE DEN BENUTZER:** Commit erstellen und pushen?

> **Hinweis:** Die Versionsnummern in `pyproject.toml`, `package.json` und `CLAUDE.md` werden NICHT lokal aktualisiert. Das übernimmt der Auto-Merge Workflow automatisch basierend auf dem Release-Label.

### 5. PR erstellen mit Release-Label

Erstelle den PR mit dem passenden `release:*` Label:
```bash
gh pr create \
  --base main \
  --head development \
  --title "Release (<type>)" \
  --label "release:<type>" \
  --body "$(cat <<'EOF'
## Release

### Changes
<CHANGELOG-Eintrag hier>

---
Release type: `<type>` — version bump happens automatically after merge via `release:<type>` label
EOF
)"
```

**ZEIGE DEM BENUTZER** den PR-Link.

> **Was danach automatisch passiert:**
> 1. CI Check läuft (Backend-Tests + Frontend-Build)
> 2. Auto-Merge merged den PR nach erfolgreichem CI
> 3. Version wird aus Label bestimmt und automatisch gebumpt (`pyproject.toml`, `package.json`, `CLAUDE.md`)
> 4. Tag `v<VERSION>` wird automatisch erstellt
> 5. GitHub Release wird aus CHANGELOG generiert
> 6. Production-Deploy wird ausgelöst
> 7. Development wird mit main synchronisiert (inkl. Version-Bump)

### 6. Fertig

Zeige Zusammenfassung:
```
Release-PR erstellt!

PR: <PR-URL>
Label: release:<type>

Automatischer Flow nach CI:
  CI ✓ → Merge → Version Bump → Tag → GitHub Release → Deploy → Sync dev
```

## Regeln

- **NIEMALS** lokal auf main mergen — immer über PR
- **NIEMALS** lokal die Version bumpen — das macht der Workflow
- **NIEMALS** ohne Bestätigung des Benutzers committen oder pushen
- **NIEMALS** `.env` oder Secrets committen
- Bei Fehlern: Abbrechen und Status anzeigen
- Bei bereits existierendem PR: Benutzer informieren und fragen ob Update gewünscht
- Commit-Message endet mit: `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
