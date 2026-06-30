# Release vorbereiten (Phase 1: CHANGELOG + Doku)

Bereitet einen Stable-Release vor: Branch `release/vX.Y.Z` mit handkuratiertem
CHANGELOG-Eintrag (`## [Unreleased]`) + ggf. README/CLAUDE.md-Updates, als PR
nach `main`. Ersetzt das stillgelegte `_release.md` (zielte auf den
retirierten `development`-Branch).

## Voraussetzung

- HEAD von `main` läuft bereits als Pre-Release auf der Production-NAS (getestet)
- `gh` CLI ist authentifiziert

## Workflow

### 1. Bump-Type vorschlagen

```bash
LAST_STABLE=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | grep -Ev -- '-(pre|rc|alpha|beta|unstable)' | sort -V | tail -1)
git fetch origin main
git log "$LAST_STABLE"..origin/main --pretty=format:'%s'
```

**Vorschlag basierend auf Commits:**
- Mindestens ein `feat!:` oder `BREAKING CHANGE:` im Body → `major`
- Mindestens ein `feat:` → `minor`
- Sonst → `patch`

**FRAGE DEN BENUTZER:** Welcher Bump-Type?

### 2. Zielversion berechnen (nur Vorschau)

```bash
NEW_VERSION=$(python scripts/bump_version.py <bump_type> --dry-run | tail -1)
echo "Zielversion: $NEW_VERSION"
```

Schreibt noch keine Dateien — der echte Bump passiert erst in Phase 2
(`/release-stable`). Grund: `deploy-production.yml`s Pre-Release-Tagging geht
davon aus, dass `pyproject.toml` zwischen Stable-Releases unverändert bleibt.

### 3. CHANGELOG-Entwurf generieren

```bash
python scripts/generate_changelog_section.py \
  --version DRAFT \
  --since "$LAST_STABLE" \
  --output -
```

Das ist nur ein **Rohentwurf** aus den Commit-Subjects (mechanisch nach
Conventional-Commits-Typ gruppiert). Verwirf die erste Zeile
(`## [DRAFT] - <date>`) komplett — sie wird durch eine bare
`## [Unreleased]`-Zeile ersetzt (Schritt 5). Überarbeite den Rest:
Formulierungen glätten, Duplikate zusammenführen, irrelevante/interne Punkte
entfernen.

**FRAGE DEN BENUTZER:** Entwurf zeigen, gemeinsam überarbeiten.

### 4. Doku-Checkliste: README.md + alle CLAUDE.md

```bash
git log "$LAST_STABLE"..origin/main --name-only --pretty=format: | sort -u
```

Gruppiere die geänderten Dateien nach Top-Level-Verzeichnis. Für jedes
Verzeichnis mit eigenem `CLAUDE.md` (siehe Liste im Root-`CLAUDE.md` unter
"Each major directory has its own CLAUDE.md"): prüfe, ob neue/entfernte
Dateien, Routen, Services oder Felder dort noch fehlen oder veraltet
beschrieben sind. Prüfe `README.md` (Feature-Liste, Quick-Reference-Links)
ebenso.

**FRAGE DEN BENUTZER:** Welche Doku-Fixes sollen jetzt mit rein?

Wende die vereinbarten Fixes als normale Edits an — sie gehören in den
gleichen Branch/Commit wie das CHANGELOG (Schritt 6).

### 5. Unreleased-Sektion einfügen

Schreibe die finale, kuratierte Sektion in eine Scratch-Datei
(`/tmp/unreleased-section.md`). Kopfzeile ist **exakt** `## [Unreleased]` —
nichts dahinter, sonst matcht `changelog_fallback.py`s Parser sie
versehentlich als echten Release:

```
## [Unreleased]

### Added

- ...

### Fixed

- ...

---

```

```bash
python scripts/insert_changelog_section.py \
  --section /tmp/unreleased-section.md \
  --target CHANGELOG.md
```

### 6. Branch + Commit + PR

```bash
git checkout -b "release/v${NEW_VERSION}" origin/main
git add CHANGELOG.md README.md  # + jede in Schritt 4 geänderte CLAUDE.md
git commit -m "chore: release v${NEW_VERSION}"
git push -u origin "release/v${NEW_VERSION}"
gh pr create \
  --base main \
  --head "release/v${NEW_VERSION}" \
  --title "chore: release v${NEW_VERSION}" \
  --label "release:<bump_type>" \
  --body "$(cat <<'EOF'
## Changelog

<kuratierte Bullet-Liste aus Schritt 3>

## Doku

<Liste der README/CLAUDE.md-Fixes aus Schritt 4, falls vorhanden>

---
Bereitet einen Stable-Release vor. Enthält keine Code-Änderungen (der Code
läuft bereits als Pre-Release in Production) -- nur CHANGELOG + Doku.

**Beim Mergen:** Squash-Merge ist auf diesem Repo deaktiviert
(`allow_squash_merge: false`). Bitte über
`gh pr merge <PR-Nummer> --merge --subject "chore: release v<Version>" --body ""`
mergen, NICHT über den Standard-"Merge pull request"-Button ohne die
Commit-Message anzupassen -- sonst greift der `chore: release v`-Skip-Filter
in `deploy-production.yml` nicht und es entsteht ein irrtümlich benannter
Pre-Release-Tag.
EOF
)"
```

**ZEIGE DEM BENUTZER** den PR-Link + den Merge-Hinweis aus dem PR-Body.

### 7. Nach dem Merge

Sobald CI grün ist und der PR (mit angepasster Commit-Message!) gemerged
wurde, übernimmt `/release-stable` (Phase 2) den eigentlichen Tag-Schritt.

## Regeln

- **NIEMALS** lokal `pyproject.toml` / `package.json` / `CLAUDE.md`-Version bumpen — das passiert erst in Phase 2.
- **NIEMALS** lokal Tags erstellen oder pushen.
- Die `## [Unreleased]`-Kopfzeile darf **nichts** nach `]` enthalten (kein `- <text>`).
- Bei bereits existierendem Release-PR: Benutzer informieren und fragen, ob Update gewünscht.
- Commit-Message endet mit: `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
