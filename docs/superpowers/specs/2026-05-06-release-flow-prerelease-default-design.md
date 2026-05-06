# Release Flow: Pre-Release als Default, manueller Stable-Trigger

**Date:** 2026-05-06
**Status:** Approved (brainstorming complete, ready for plan)
**Branch:** `feature/release-flow-prerelease-default` (to be created from `development`)

## Problem

Heute wird bei jedem PR `development → main` mit `release:patch|minor|major` Label automatisch ein Stable-Release erzeugt: Version-Bump in `pyproject.toml` / `package.json` / `CLAUDE.md`, Tag `vX.Y.Z`, GitHub-Release als „Latest", Production-Deploy.

Das passt nicht zur Realität: Features brauchen Zeit auf der echten NAS, bis klar ist, dass sie stabil laufen. Ein PR-Merge ist häufig nicht der Moment für einen offiziellen Stable-Release. Aktuell sind dadurch potenziell instabile Versionen als „Latest" markiert (relevant für den `STABLE`-Update-Channel und das `BaluHost-Plugin-Market`-Repo, das `min_baluhost_version` referenziert).

## Solution (1-Satz)

PR-Merges auf `main` erzeugen **Pre-Release-Tags** statt Stable-Releases (Production-Deploy bleibt unverändert); ein neuer manueller `workflow_dispatch`-Workflow `release-stable.yml` promotet HEAD bei Bedarf zu einem Stable-Release mit Bump + Auto-CHANGELOG.

## Goals

- Jeder PR-Merge auf `main` → Production-Deploy + Pre-Release-Tag `v<last_stable>-pre.<run_number>`
- `pyproject.toml` / `package.json` / `CLAUDE.md` werden bei Pre-Releases **nicht** verändert
- Manueller Stable-Trigger (GH UI oder Slash-Command) → Bump + CHANGELOG-Sektion + Stable-Tag + GitHub-Release als „Latest"
- BaluHost-UI zeigt Pre-Release-Version + Badge an
- CHANGELOG-Sektionen werden beim Stable-Trigger automatisch aus Conventional Commits generiert (kein manuelles Pflegen mehr)

## Non-Goals

- Keine Änderung am Production-Deploy-Skript (`/opt/baluhost/deploy/scripts/ci-deploy.sh`)
- Keine zweite Maschine / kein Staging-Setup
- Keine Änderung am Pi-Frontend-Deploy (`deploy-pi.yml`) — bleibt path-gefiltert wie heute
- Keine Änderung am Update-Service-Channel-Modell (`STABLE` / `UNSTABLE` / `DEVELOPMENT`) — der bestehende `is_prerelease`-Flag in `ReleaseInfo` wird vom neuen Tag-Schema bereits korrekt gefüllt
- Keine Anpassung der bestehenden Branch-Protection-Regeln (falls welche existieren — wird im Plan separat geprüft)

## Architecture

```
Feature-Arbeit                                Manueller Stable-Release
───────────────                                ────────────────────────

   development                                GitHub UI / gh CLI
       │  (PR development → main)             "Run workflow"
       ▼                                        bump_type: patch|minor|major
   ci-check.yml ──────────────► PASSES              │
       │                                            ▼
       ▼                                       release-stable.yml (NEW)
   auto-merge.yml (modified)                       │
       │                                           ├─ Read CURRENT_VERSION
       ├─ Mergt PR                                 │  from pyproject.toml
       ├─ KEINE Versions-Bumps                     ├─ Compute NEW_VERSION
       ├─ KEIN release:* Label nötig               ├─ Generate CHANGELOG section
       ├─ Tag: v${CURRENT}-pre.${RUN}              │  from conventional commits
       ├─ Push tag                                 ├─ python scripts/bump_version.py
       │                                           ├─ commit "chore: release v${NEW}"
       ▼                                           ├─ push origin main
   Push to main                                    ├─ tag vNEW (no -pre suffix)
       │                                           └─ push tag
       ├─► deploy-production.yml ──► NAS deployt
       │  (skip filter blocks "chore: release v" too)
       │
       ├─► deploy-pi.yml (only if client/** changed)
       │
       └─► create-release.yml triggert auf Tag-Push
           - "-pre.*" → marked als "Pre-Release"
           - sonst → marked als "Latest"
```

**Key invariants:**
1. `pyproject.toml` ist single source of truth für **Stable**-Version. Pre-Releases verändern keine Versions-Dateien.
2. Pre-Release-Tag-Schema: `v<pyproject_version>-pre.<github_run_number>`. Run number ist monoton steigend pro Repo, garantiert eindeutig.
3. Stable-Trigger schreibt **einen** Commit auf main (`chore: release vX.Y.Z`) + **einen** Tag (`vX.Y.Z`). Beide werden vom Skip-Filter im Production-Deploy gefangen, weil der Code identisch zum letzten Pre-Release ist.
4. GitHub-Release-Klassifizierung erfolgt automatisch in `create-release.yml` über Tag-Suffix-Pattern.

## Components

### 1. Pre-Release-Tagging in `auto-merge.yml`

**Datei:** `.github/workflows/auto-merge.yml`

**Entfernt:**
- Job-Step „Bump version from release label" (Zeile ~57-75)
- Lesen des `release:*` Labels und Berechnen von `BUMP_TYPE`/`NEW_VERSION`
- `python3 scripts/bump_version.py "$BUMP_TYPE"`
- Commit `chore: bump version to v${NEW_VERSION}` und Push

**Geändert:**
- Job-Step „Auto-tag from pyproject.toml" wird umbenannt zu „Auto-tag pre-release" und nutzt:
  ```yaml
  - name: Auto-tag pre-release
    working-directory: /tmp/repo
    env:
      RUN_NUMBER: ${{ github.event.workflow_run.run_number }}
    run: |
      VERSION=$(grep -oP '^version\s*=\s*"\K[^"]+' backend/pyproject.toml)
      TAG="v${VERSION}-pre.${RUN_NUMBER}"
      if git tag -l "$TAG" | grep -q .; then
        echo "Tag $TAG already exists — skipping"
      else
        echo "Creating pre-release tag $TAG"
        git tag -a "$TAG" -m "Pre-release $TAG"
        git push origin "$TAG"
      fi
  ```
- `RUN_NUMBER` kommt aus dem auslösenden CI-Check-Workflow-Run, damit pro PR-Merge eindeutig

**Unverändert:**
- Job-Step „Find and merge PR" — mergt PR, löscht Branch (außer `development`)
- Job-Step „Sync development with main" — bleibt wichtig damit `development` Stable-Bumps + CHANGELOG übernimmt

### 2. Neuer Workflow `release-stable.yml`

**Datei:** `.github/workflows/release-stable.yml` (CREATE)

**Trigger:** `workflow_dispatch` mit Input `bump_type` (Choice: `patch` / `minor` / `major`)

**Permissions:** `contents: write`

**Steps:**

```yaml
name: Release Stable

on:
  workflow_dispatch:
    inputs:
      bump_type:
        description: "Semver bump for the new stable release"
        type: choice
        required: true
        options: [patch, minor, major]

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # need full history for git log
          token: ${{ secrets.DEPLOY_PAT }}

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Configure git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

      - name: Compute next version
        id: version
        env:
          BUMP_TYPE: ${{ inputs.bump_type }}
        run: |
          CURRENT=$(grep -oP '^version\s*=\s*"\K[^"]+' backend/pyproject.toml)
          NEW=$(python scripts/bump_version.py "$BUMP_TYPE" --dry-run | tail -1)
          echo "current=$CURRENT" >> "$GITHUB_OUTPUT"
          echo "new=$NEW" >> "$GITHUB_OUTPUT"
          echo "Bumping $CURRENT → $NEW"

      - name: Find last stable tag
        id: last_stable
        run: |
          # Stable tags match v*.*.* but NOT *-pre.* / *-rc.* / *-alpha* / *-beta*
          LAST=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | grep -Ev -- '-(pre|rc|alpha|beta|unstable)' | sort -V | tail -1)
          if [ -z "$LAST" ]; then
            echo "No previous stable tag found; using initial commit"
            LAST=$(git rev-list --max-parents=0 HEAD)
          fi
          echo "ref=$LAST" >> "$GITHUB_OUTPUT"
          echo "Last stable: $LAST"

      - name: Generate CHANGELOG section
        id: changelog
        env:
          NEW_VERSION: ${{ steps.version.outputs.new }}
          LAST_REF: ${{ steps.last_stable.outputs.ref }}
        run: |
          python scripts/generate_changelog_section.py \
            --version "$NEW_VERSION" \
            --since "$LAST_REF" \
            --output /tmp/changelog-section.md
          # Fail if section is empty (no commits since last stable)
          if ! grep -q '^- ' /tmp/changelog-section.md; then
            echo "::error::No conventional-commit changes since $LAST_REF — refusing to create empty release"
            exit 1
          fi

      - name: Insert CHANGELOG section
        run: |
          # Prepend the new section directly after the file header (line 1: "# Changelog")
          python scripts/insert_changelog_section.py \
            --section /tmp/changelog-section.md \
            --target CHANGELOG.md

      - name: Bump version files
        env:
          BUMP_TYPE: ${{ inputs.bump_type }}
        run: python scripts/bump_version.py "$BUMP_TYPE"

      - name: Commit + push
        env:
          NEW_VERSION: ${{ steps.version.outputs.new }}
        run: |
          git add backend/pyproject.toml client/package.json CLAUDE.md CHANGELOG.md
          git commit -m "chore: release v${NEW_VERSION}"
          git push origin main

      - name: Tag + push
        env:
          NEW_VERSION: ${{ steps.version.outputs.new }}
        run: |
          TAG="v${NEW_VERSION}"
          git tag -a "$TAG" -m "Release $TAG"
          git push origin "$TAG"
          echo "Stable release tag $TAG pushed — create-release.yml will create the GitHub Release"
```

**Edge-Cases:**
- Kein Commit seit letztem Stable → `generate_changelog_section.py` produziert leere Sektion → Workflow bricht ab
- `--dry-run` Flag in `bump_version.py` muss ergänzt werden (siehe Section 5)

### 3. Skip-Filter erweitern in `deploy-production.yml`

**Datei:** `.github/workflows/deploy-production.yml`

**Geändert:**
```yaml
# vorher:
if: "!startsWith(github.event.head_commit.message, 'chore: bump version')"

# nachher:
if: "!startsWith(github.event.head_commit.message, 'chore: bump version') && !startsWith(github.event.head_commit.message, 'chore: release v')"
```

Der Stable-Trigger pusht einen `chore: release vX.Y.Z`-Commit auf main. Production läuft schon auf demselben Code (vom letzten Pre-Release-Deploy), daher überspringt der Filter den redundanten Deploy.

### 4. Pre-Release-Erkennung in `create-release.yml`

**Datei:** `.github/workflows/create-release.yml`

**Geändert:** Step „Determine pre-release" erweitern um `*-pre.*` Pattern:

```bash
if [[ "$TAG" == *-pre.* ]] || [[ "$TAG" == *-alpha* ]] || [[ "$TAG" == *-beta* ]] || [[ "$TAG" == *-unstable* ]] || [[ "$TAG" == *-rc* ]]; then
  echo "flag=--prerelease" >> "$GITHUB_OUTPUT"
else
  echo "flag=" >> "$GITHUB_OUTPUT"
fi
```

**Unverändert:** Auto-Notes aus CHANGELOG (für Stable) bzw. Fallback auf `gh api .../releases/generate-notes` (für Pre-Releases — CHANGELOG enthält keine Pre-Release-Sektionen).

### 5. CHANGELOG-Guard entfernen + Helper-Skripte

**Datei:** `.github/workflows/ci-check.yml`

**Entfernt:** Job `changelog-guard` (Zeilen 57-100). Es gibt keine `release:*` Labels mehr.

**Datei:** `scripts/bump_version.py`

**Geändert:** `--dry-run` Flag hinzufügen, das die berechnete neue Version auf stdout ausgibt ohne Dateien zu verändern. Wird vom `release-stable.yml`-Workflow genutzt.

```python
# Pseudocode-Erweiterung am Ende von main():
if "--dry-run" in sys.argv:
    print(new_version)
    return
# (existing) update_pyproject(...) etc.
```

**Datei:** `scripts/generate_changelog_section.py` (CREATE)

Liest Conventional-Commits-Subjects aus `git log $SINCE..HEAD --pretty=format:'%s|%H'`, gruppiert nach Typ:

| Conventional-Commits-Typ | CHANGELOG-Sektion |
|--------------------------|-------------------|
| `feat:` (auch mit Scope) | `### Added` |
| `fix:` | `### Fixed` |
| `refactor:`, `perf:`     | `### Changed` |
| `docs:` | `### Documentation` |
| `feat!:`, `BREAKING CHANGE:` im Body | `### ⚠ BREAKING CHANGES` (zuoberst) |
| `chore:`, `ci:`, `test:`, `style:`, `build:` | **ignoriert** |
| Subjects ohne Conventional-Commits-Präfix | **ignoriert** (sauberer CHANGELOG) |

Format-Beispiel:
```markdown
## [1.32.0] - 2026-05-06

### Added

- **(sleep)** detect Suspend + WoL capabilities via sudo (#70)
- new dashboard widget for power profiles (#73)

### Fixed

- prevent empty release notes — generate-notes fallback + label guard (#68)
```

Zusatz-Logik:
- Scope (z.B. `feat(sleep):`) wird als `**(sleep)**` rendered
- PR-Nummer aus Merge-Commit-Subject extrahieren (`Merge pull request #X` Pattern oder ` (#X)` am Ende des Subjects)
- BREAKING-Changes im Commit-Body (mehrzeilige `git log --pretty=format:'%s%n%n%b'`) werden gesondert geparst und in eigene Sektion gepackt

**Datei:** `scripts/insert_changelog_section.py` (CREATE)

Klein, ~30 Zeilen: liest `--section` und `--target`, fügt die neue Sektion direkt nach der ersten H1-Zeile (`# Changelog`) ein, mit `---`-Separator dazwischen passend zum bestehenden Stil.

### 6. Backend Version-Endpoint anpassen

**Dateien:**
- `backend/app/services/update/prod_backend.py:60-91` (`get_current_version`)
- `backend/app/services/update/dev_backend.py:46-54` (`get_current_version`)
- `backend/app/schemas/update.py` (`VersionInfo`)

**Schema-Erweiterung in `VersionInfo`:**
```python
class VersionInfo(BaseModel):
    version: str           # "1.31.7-pre.42" oder "1.32.0"
    commit: str
    commit_short: str
    tag: Optional[str]     # "v1.31.7-pre.42" oder "v1.32.0" oder None
    date: Optional[datetime]
    is_dev_build: bool     # True nur bei lokalem Build ohne exakten Tag
    is_prerelease: bool    # NEW — True wenn Tag ein Pre-Release-Suffix hat
```

**Neue Logik in `ProdUpdateBackend.get_current_version()`:**
```python
async def get_current_version(self) -> VersionInfo:
    # Try exact tag match (will succeed for pre-release and stable tags pushed by CI)
    exact_ok, exact_tag, _ = self._run_git("describe", "--tags", "--exact-match")
    if exact_ok and exact_tag.strip():
        tag = exact_tag.strip()
        version = tag.lstrip("v")
        is_prerelease = any(
            marker in tag for marker in ("-pre.", "-rc.", "-alpha", "-beta", "-unstable")
        )
        is_dev_build = False
    else:
        # Local build between tags — fall back to pyproject.toml
        version = version_to_string(get_installed_version())
        tag = None
        is_prerelease = False
        is_dev_build = True

    success, commit, _ = self._run_git("rev-parse", "HEAD")
    if not success:
        commit = "unknown"

    success, date_str, _ = self._run_git("log", "-1", "--format=%cI")
    date = datetime.fromisoformat(date_str) if success and date_str else None

    return VersionInfo(
        version=version,
        commit=commit,
        commit_short=commit[:7] if commit != "unknown" else "unknown",
        tag=tag,
        date=date,
        is_dev_build=is_dev_build,
        is_prerelease=is_prerelease,
    )
```

**`DevUpdateBackend.get_current_version()`:** Setzt `is_prerelease=False`, `is_dev_build=True` (unverändert), liefert simulierte Stable-Version.

**Endpoint:** `GET /api/updates/version` (public, no auth, in `backend/app/api/routes/updates.py:38-49`) bleibt strukturell unverändert — Response-Shape erweitert sich automatisch.

### 7. Frontend — Pre-Release-Anzeige

**Datei:** `client/src/api/updates.ts`

**Geändert:** Interface `VersionInfo` um `is_prerelease: boolean` erweitern.

**Datei:** `client/src/contexts/VersionContext.tsx`

`VersionProvider` lädt `getPublicVersion()` einmal beim Mount und stellt `fullVersion: VersionInfo | null` über `useVersion()` zur Verfügung. Provider-Logik bleibt unverändert — der zusätzliche Boolean steht automatisch in `fullVersion.is_prerelease`.

**Geändert:** Helper `useFormattedVersion()`. Aktuell:
```typescript
return `${prefix} v${version}`;
```

Neu (zusätzliche Hook-Variante für Anzeigen, die auch das Pre-Release-Badge brauchen):
```typescript
export function useVersionDisplay(prefix: string = 'BaluHost OS'): {
  text: string;
  isPrerelease: boolean;
} {
  const { fullVersion, loading, error } = useVersion();
  if (loading) return { text: `${prefix} v...`, isPrerelease: false };
  if (error || !fullVersion) return { text: `${prefix} v?.?.?`, isPrerelease: false };
  return {
    text: `${prefix} v${fullVersion.version}`,
    isPrerelease: fullVersion.is_prerelease,
  };
}
```

`useFormattedVersion()` bleibt für Rückwärts-Kompatibilität (rein String-basiert) — Stellen die das Badge brauchen wechseln auf `useVersionDisplay()`.

**Konsumenten** (im Plan zu identifizieren — minimum):
- `client/src/pages/UpdatePage.tsx` und/oder Tab-Components in `client/src/components/updates/` — primärer Anzeigeort
- Layout/Footer falls Version dort gerendert wird (`useFormattedVersion()` Aufrufer suchen)

**Pre-Release-Badge:** kleines Tailwind-Span neben dem Versions-Text:
```tsx
{isPrerelease && (
  <span className="ml-2 inline-flex items-center rounded-md bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-300">
    {t('updates.preRelease.badge')}
  </span>
)}
```

**i18n-Keys:**

`client/src/i18n/locales/en/updates.json`:
```json
"preRelease": {
  "badge": "Pre-Release"
}
```

`client/src/i18n/locales/de/updates.json`:
```json
"preRelease": {
  "badge": "Pre-Release"
}
```

### 8. Slash-Commands

**Datei:** `.claude/commands/release/_release.md` (MODIFY)

Vereinfachte Version (Label/CHANGELOG-Schreiben raus, da beides nicht mehr gebraucht wird):

```markdown
# Release-PR: development → main

Erstelle einen PR von `development` nach `main`. Jeder Merge erzeugt automatisch ein Pre-Release-Tag und deployt auf Production. Stable-Releases werden separat über `/release-stable` getriggert.

## Workflow

### 1. Branch-Check
Verifiziere `development`-Branch. Falls nicht: abbrechen.

### 2. Commits seit letztem Stable anzeigen
```bash
git log $(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | grep -Ev -- '-(pre|rc|alpha|beta|unstable)' | sort -V | tail -1)..HEAD --oneline
```

### 3. PR erstellen
```bash
gh pr create --base main --head development \
  --title "<auto-generated from commit subjects>" \
  --body "<list of commits>"
```

### 4. Hinweis auf automatischen Flow
- CI Check läuft → Auto-Merge → Pre-Release-Tag `v<current>-pre.<run>` → Deploy
- KEIN Stable-Release, KEIN Bump in pyproject.toml/package.json/CLAUDE.md
- Für Stable-Release: `/release-stable` separat ausführen

## Regeln
- NIEMALS lokal auf main mergen
- NIEMALS lokal Versionen bumpen
- NIEMALS Tags manuell pushen
```

**Datei:** `.claude/commands/release/_release-stable.md` (CREATE)

```markdown
# Release Stable

Triggert den `release-stable.yml` Workflow auf GitHub, der HEAD von `main` zu einem stabilen Release promotet (Bump + CHANGELOG-Sektion + Stable-Tag + GitHub-Release als „Latest").

## Workflow

### 1. Bump-Type bestimmen
Analysiere Commits seit letztem Stable-Tag:
```bash
LAST_STABLE=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | grep -Ev -- '-(pre|rc|alpha|beta|unstable)' | sort -V | tail -1)
git log "$LAST_STABLE"..origin/main --pretty=format:'%s'
```

**Vorschlag basierend auf Commits:**
- Mindestens ein `feat!:` oder `BREAKING CHANGE:` im Body → `major`
- Mindestens ein `feat:` → `minor`
- Sonst → `patch`

**Frage Nutzer:** Welcher Bump-Type? (Vorschlag anzeigen)

### 2. CHANGELOG-Vorschau
Zeige geplante neue Version + Vorschau der CHANGELOG-Sektion (lokal generiert via `python scripts/generate_changelog_section.py --version <NEW> --since "$LAST_STABLE" --output -`). Nur als Vorschau — der echte CHANGELOG wird im Workflow geschrieben.

### 3. Bestätigung + Trigger
**Frage Nutzer:** Trigger ausführen?

```bash
gh workflow run release-stable.yml --ref main -f bump_type=<type>
```

### 4. Status-Link anzeigen
```bash
gh run list --workflow=release-stable.yml --limit 1
```

## Regeln
- Workflow läuft auf `main` (nicht `development`)
- Lokale `development`-Branch wird nach Stable-Release vom Auto-Merge-Workflow synchronisiert (existing logic)
- NIEMALS lokal `pyproject.toml`/`package.json`/`CLAUDE.md` bumpen
- NIEMALS lokal Stable-Tags erstellen oder pushen
```

## Data Flow

### Pre-Release Flow (jeder PR-Merge)

1. PR `development → main` wird erstellt
2. `ci-check.yml` läuft (backend-tests, frontend-build) — kein `changelog-guard` mehr
3. `auto-merge.yml` triggert auf `workflow_run: completed` von CI Check
4. Mergt PR via `gh pr merge`
5. Liest `version` aus `backend/pyproject.toml` (z.B. `1.31.7`)
6. Erstellt Tag `v1.31.7-pre.${GITHUB_RUN_NUMBER}`, pusht
7. Push auf main triggert `deploy-production.yml` → ci-deploy.sh → NAS deployt
8. Tag-Push triggert `create-release.yml` → erkennt `-pre.` → GitHub-Release als „Pre-Release"
9. `auto-merge.yml` finalen Step: Sync `development` mit `main` (FF only)

### Stable Flow (manuell, selten)

1. User entscheidet: aktueller `main` ist gut, soll Stable werden
2. User triggert `release-stable.yml` via GH UI oder `/release-stable` Slash-Command
3. Workflow checkt main aus, liest `CURRENT_VERSION` aus pyproject.toml
4. Berechnet `NEW_VERSION` via `python scripts/bump_version.py <bump_type> --dry-run`
5. Findet `LAST_STABLE_TAG` (Tag-Liste filtern auf Stable-Pattern)
6. Generiert CHANGELOG-Sektion aus Commits seit `LAST_STABLE_TAG` via `scripts/generate_changelog_section.py`
7. Bricht ab falls Sektion leer
8. Inserted Sektion in CHANGELOG.md direkt nach der H1-Zeile (`# Changelog`), vor existierenden Sektionen
9. `python scripts/bump_version.py <bump_type>` → bumpt 3 Dateien
10. Commit `chore: release v${NEW_VERSION}` mit allen 4 Dateien
11. Push auf main
12. Tag `v${NEW_VERSION}` (kein Suffix), Push
13. Push triggert `deploy-production.yml` — wird durch erweiterten Skip-Filter geblockt (kein redundanter Deploy)
14. Tag-Push triggert `create-release.yml` — kein `-pre.` → GitHub-Release als „Latest"
15. `auto-merge.yml`-Sync-Logik triggert nicht (kein PR-Merge), aber: nächster `development → main` PR pickt die neue Stable-Version + CHANGELOG-Aktualisierung mit, weil `auto-merge.yml`-Sync-Step `git merge origin/main --ff-only` macht

### Versions-Anzeige in der UI

1. Frontend lädt beim Mount `getPublicVersion()` (Rate-limited public endpoint)
2. Backend: `git describe --tags --exact-match` auf HEAD
   - Auf Production: HEAD ist immer auf einem Tag (Pre-Release oder Stable, ggf. nach Stable-Bump-Commit kurzzeitig nicht — aber dann wird via `is_dev_build` gehandhabt)
   - Auf Dev: simulierter Wert
3. `VersionInfo` enthält `version` (z.B. `1.31.7-pre.42`) + `is_prerelease`
4. `useVersionDisplay()` Hook liefert `{text, isPrerelease}` an Konsumenten
5. Anzeige: Text + optionales amber-Badge

## Error Handling

| Szenario | Verhalten |
|----------|-----------|
| Pre-Release-Tag bereits vorhanden (Run-Number-Kollision, theoretisch) | `auto-merge.yml` loggt Skip, deploy läuft trotzdem |
| `release-stable.yml` ohne Commits seit letztem Stable | Workflow bricht mit Error ab (`generate_changelog_section.py` exit code) |
| `release-stable.yml` während laufender Pre-Release-Pipeline | Eigener Run, kein Concurrency-Lock — sein Push triggert wieder `deploy-production.yml` der durch `concurrency: production-deploy` gequeued wird |
| `bump_version.py --dry-run` neu ergänzt | Falls altes Skript verwendet wird ohne Flag → Workflow scheitert beim ersten Test (TDD im Plan) |
| `git describe --tags --exact-match` schlägt fehl (lokal/dev) | Fallback auf pyproject.toml → `version=1.31.7`, `is_dev_build=true`, `is_prerelease=false` |
| Skip-Filter im Production-Deploy fängt Stable-Bump-Commit nicht | Redundanter Deploy mit identischem Code, kein Schaden, aber sichtbar in Run-History — wird im Plan als Test verifiziert |
| Tag-Push schlägt fehl (Permissions) | `auto-merge.yml`/`release-stable.yml` loggt Error, Tag muss manuell nachgepusht werden — kein automatisches Retry |
| User mit `release:*` Label auf altem PR mergt nach Rollout | Label hat keinen Effekt mehr — Pre-Release-Tag wird trotzdem korrekt erzeugt |

## Testing

### Manuell (Dev-Mode + Live-Test)

1. **Pre-Release-Flow E2E:**
   - Branch von `development` → kleine Änderung → PR auf main → mergen
   - Verify: Tag `v<aktuelle>-pre.<N>` existiert auf GitHub
   - Verify: GitHub-Release angelegt, markiert als „Pre-Release"
   - Verify: Production-Deploy läuft (Logs in `journalctl -u baluhost-backend -f`)
   - Verify: `pyproject.toml`/`package.json`/`CLAUDE.md` unverändert
   - Verify: BaluHost-UI zeigt `v<aktuelle>-pre.<N>` mit Pre-Release-Badge

2. **Stable-Flow:**
   - `/release-stable` mit `bump_type=patch` ausführen
   - Verify: Workflow erfolgreich
   - Verify: Neuer Stable-Tag, GitHub-Release als „Latest"
   - Verify: pyproject.toml/package.json/CLAUDE.md gebumpt
   - Verify: CHANGELOG.md hat neue Sektion mit korrekt gruppierten Conventional-Commits-Einträgen
   - Verify: Production-Deploy wurde übersprungen (Logs)
   - Verify: BaluHost-UI zeigt jetzt Stable-Version, kein Badge

3. **Edge: Stable ohne Commits:**
   - Sofort nach Stable-Trigger nochmal triggern
   - Verify: Workflow bricht mit Error ab

### Unit-Tests (im Plan zu schreiben)

- `scripts/generate_changelog_section.py`: Tests für Conventional-Commits-Parsing, Scope-Extraktion, BREAKING-Detection, PR-Number-Extraktion, leere Sektion → exit 1
- `scripts/insert_changelog_section.py`: Test für Insertion an korrekter Stelle, Beibehaltung des Trennzeichens
- `scripts/bump_version.py`: Test für `--dry-run` Mode (keine Datei-Änderungen, korrekte Ausgabe auf stdout)
- `backend/app/services/update/prod_backend.py::get_current_version`: Tests mit gemocktem `_run_git` für (a) HEAD auf Pre-Release-Tag, (b) HEAD auf Stable-Tag, (c) HEAD zwischen Tags

### CI-Tests

- Bestehende `ci-check.yml` (backend-tests + frontend-build) bleibt unverändert
- Manuell verifizieren dass `changelog-guard` weg ist und PRs ohne CHANGELOG-Änderung durchlaufen

## Migration / Rollout

**Reihenfolge der Implementierung** (im Plan zu detaillieren):

1. **Phase 1 — Backend-Änderungen** (deploybar ohne Workflow-Änderungen):
   - `bump_version.py --dry-run` Flag
   - `scripts/generate_changelog_section.py` + `scripts/insert_changelog_section.py`
   - `VersionInfo.is_prerelease` Schema-Feld + Backend-Logik
   - Frontend `useVersionDisplay()` + Badge + i18n
   - Tests

2. **Phase 2 — Workflow-Switch** (atomar deployen):
   - Neuer `release-stable.yml`
   - `auto-merge.yml` Pre-Release-Tagging statt Stable-Bump
   - `deploy-production.yml` erweiterter Skip-Filter
   - `create-release.yml` `-pre.` Pattern
   - `ci-check.yml` `changelog-guard` entfernen
   - Slash-Commands `_release.md` umbauen + `_release-stable.md` neu

3. **Phase 3 — Cleanup:**
   - Memory-Eintrag `feedback_release_workflow.md` aktualisieren (neue Pre-Release-Semantik dokumentieren)
   - Alte offene PRs mit `release:*` Label prüfen — Label entfernen oder mergen vor Phase-2-Switch
   - `release:patch|minor|major` Labels im Repo löschen (optional, aber sauber)

**Atomarität:** Phase 2 muss in einem PR/Merge passieren, sonst gibt es zwischen Workflow-Updates inkonsistente Zustände (z.B. neuer `auto-merge.yml` ohne neuen Skip-Filter im Deploy).

## File Changes Summary

| Datei | Aktion | Zweck |
|-------|--------|-------|
| `.github/workflows/release-stable.yml` | **Create** | Manuelle Stable-Promotion via workflow_dispatch |
| `.github/workflows/auto-merge.yml` | Modify | Pre-Release-Tags statt Stable-Bump; Bump-Step entfernen |
| `.github/workflows/deploy-production.yml` | Modify | Skip-Filter um `chore: release v` erweitern |
| `.github/workflows/create-release.yml` | Modify | `-pre.` als Prerelease-Suffix erkennen |
| `.github/workflows/ci-check.yml` | Modify | `changelog-guard` Job entfernen |
| `backend/app/services/update/prod_backend.py` | Modify | Tag-basierte Version + `is_prerelease` |
| `backend/app/services/update/dev_backend.py` | Modify | `is_prerelease=False` mocken |
| `backend/app/schemas/update.py` | Modify | `is_prerelease: bool` zu `VersionInfo` |
| `backend/tests/services/test_update_service.py` | Modify | Tests für neue Tag-Detection |
| `client/src/api/updates.ts` | Modify | `is_prerelease` zu `VersionInfo` interface |
| `client/src/contexts/VersionContext.tsx` | Modify | `useVersionDisplay()` Hook ergänzen |
| `client/src/pages/UpdatePage.tsx` (oder relevante Tab-Components) | Modify | Pre-Release-Badge anzeigen |
| `client/src/i18n/locales/de/updates.json` | Modify | `preRelease.badge` Key |
| `client/src/i18n/locales/en/updates.json` | Modify | `preRelease.badge` Key |
| `scripts/bump_version.py` | Modify | `--dry-run` Flag |
| `scripts/generate_changelog_section.py` | **Create** | Conventional-Commits → CHANGELOG-Sektion |
| `scripts/insert_changelog_section.py` | **Create** | Insert-Helper für CHANGELOG.md |
| `.claude/commands/release/_release.md` | Modify | Vereinfacht — kein Label, kein CHANGELOG-Schreiben |
| `.claude/commands/release/_release-stable.md` | **Create** | Stable-Trigger via `gh workflow run` |

## Open Questions / Defer

- **Stable-Release-Channel-Mapping im Update-Service:** Der `services/update/` filtert Releases nach Channel. Aktuell vermutlich `STABLE` = nicht-prerelease, `UNSTABLE` = prerelease. Das passt automatisch zum neuen Schema (`is_prerelease=true` bei `-pre.*`). Verifikation im Plan: existing `ReleaseInfo.is_prerelease` Logic in `prod_backend.py::get_all_releases()` checken.
- **`release:patch|minor|major` Labels im Repo:** Können nach erfolgreichem Rollout gelöscht werden. Nicht blockierend für die Implementierung — können stehen bleiben (sind dann no-ops).
- **Branch-Protection auf main:** Falls eingerichtet, ggf. anpassen damit `release-stable.yml` Bot direkt pushen darf (DEPLOY_PAT muss Rechte haben). Im Plan zu verifizieren.
