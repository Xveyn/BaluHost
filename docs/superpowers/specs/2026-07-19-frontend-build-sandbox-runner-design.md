# `frontend-build` auf den ci-sandbox-Runner verlagern

**Datum:** 2026-07-19
**Betroffen:** `.github/workflows/ci-check.yml`, `scripts/configure-ci.sh`,
`ci-config.example.conf`, `scripts/bootstrap-ci-runner.sh`,
`.claude/rules/ci-cd-security.md`
**Baut auf:** PR #420 (`ci-tests`-Environment-Gate scharfgeschaltet). Ohne #420
ist dieser Umzug **nicht** sicher — siehe „Reihenfolge".

## Ziel

`frontend-build` läuft heute auf `ubuntu-latest`. Es soll auf den gehärteten
`ci-sandbox`-Runner auf BaluNode wandern, unter derselben zweischichtigen
Isolation und derselben Freigabepflicht wie `backend-tests`.

Damit gilt die Regel, die Xveyn gesetzt hat: **alles, was PR-getriggert auf
BaluNode läuft, braucht einen manuellen Freigabe-Klick.**

Nicht-Ziel: Playwright, `raid-mdadm-loopback`, `tauri-build`, `tui-build`,
`deploy-pi` und die Release-Workflows bleiben, wo sie sind.
`raid-mdadm-loopback` ist ausdrücklich gesperrt — echtes `mdadm` auf eigener
Hardware kann Platten zerstören.

## Ist-Zustand

`frontend-build` (`ci-check.yml`): `ubuntu-latest`, `actions/setup-node@v5` mit
`cache: 'npm'`, dann `npm ci`, `npx eslint .`, `npm run build`,
`npm run test:coverage`, plus ein Coverage-Summary-Schritt, der auf dem Host
`node -e` ausführt. Laufzeit zuletzt 4m46s.

`backend-tests` liefert das Muster, das gespiegelt wird: Runner-Auswahl per
`fromJSON`-Ausdruck, `environment: ci-tests` bedingt auf `pull_request`,
Runner-Identity-Tripwire, und **ein** `podman run` gegen ein gepinntes Image,
in dem der gesamte untrusted Code läuft.

Der Bootstrap installiert **kein** Node auf dem Host (nur podman, uidmap,
passt, slirp4netns, fuse-overlayfs, dbus-user-session) und zieht das
Python-Testimage vorab.

## Entscheidungen (mit Xveyn abgestimmt)

### 1. Kein npm-Cache — `npm ci` frisch pro Lauf

Ein Cache, in den PR-Code schreiben darf, ist geteilter veränderlicher Zustand
zwischen PRs: ein bösartiger PR könnte ein Paket vergiften, das ein späterer
Lauf arglos verwendet. `backend-tests` macht `pip install` aus demselben Grund
frisch. Kosten: ~30–60 s pro Lauf, die die schnellere Hardware weitgehend
kompensiert.

Konsequenz: `actions/setup-node` entfällt ersatzlos.

### 2. Eigene Fork-Variable `FRONTEND_BUILD_RUNNER`

Nicht `BACKEND_TEST_RUNNER` mitbenutzen — der Name würde dann nicht mehr
beschreiben, was er steuert. Eine eigene Variable hält beide Jobs unabhängig
wählbar und ist keine Breaking Change für Forks, die `BACKEND_TEST_RUNNER`
bereits gesetzt haben.

Upstream bleibt hartkodiert (`github.repository == 'Xveyn/BaluHost'`); PR-Code
kann die Runner-Wahl über keinen der beiden Wege beeinflussen.

### 3. Zweite Runner-Instanz gegen Serialisierung

**Ein Self-Hosted-Runner führt immer nur einen Job gleichzeitig aus.** Heute
laufen `backend-tests` (9m43s, Sandbox) und `frontend-build` (4m46s,
GitHub-VM) parallel → PR-CI nach ~10 min durch. Auf einem einzigen Runner
würden sie serialisieren → ~14–15 min.

Deshalb: eine zweite Runner-Instanz auf derselben Box, gleicher `ci-runner`-User,
gleiches Label `ci-sandbox`, eigener systemd-Service. Beide Jobs laufen wieder
parallel.

## Änderungen

### A. `ci-check.yml` — `frontend-build`

```yaml
frontend-build:
  runs-on: ${{ fromJSON(github.repository == 'Xveyn/BaluHost' && '["self-hosted","ci-sandbox"]' || vars.FRONTEND_BUILD_RUNNER || '"ubuntu-latest"') }}
  environment: ${{ (github.event_name == 'pull_request' && (github.repository == 'Xveyn/BaluHost' || contains(vars.FRONTEND_BUILD_RUNNER, 'self-hosted'))) && 'ci-tests' || '' }}
  timeout-minutes: 15

  steps:
    - uses: actions/checkout@v5

    - name: Assert runner identity (defense-in-depth tripwire)
      if: github.repository == 'Xveyn/BaluHost'
      # identisch zum backend-tests-Tripwire

    - name: Lint + build + unit tests (with coverage) in rootless Podman container
      env:
        NODE_IMAGE: docker.io/library/node:20-slim
      run: |
        podman run --rm \
          --network=bridge \
          -v "${{ github.workspace }}:/work:Z" \
          -w /work/client \
          "$NODE_IMAGE" \
          bash -c "set -euo pipefail; npm ci && npx eslint . && npm run build && npm run test:coverage"

    - name: Frontend coverage → job summary
      if: always()
      # node -e läuft im selben gepinnten Image, nicht auf dem Host
```

Die Job-ID bleibt `frontend-build` — der Required-Status-Check auf `main`
bricht dadurch nicht.

`node:20-slim` spiegelt die bisherige `node-version: '20'`.

### B. Fork-Konfiguration

`ci-config.example.conf`: `FRONTEND_BUILD_RUNNER=github` plus
auskommentiertes `FRONTEND_BUILD_RUNNER_LABELS`, mit demselben Kommentarstil
wie der Backend-Block.

`scripts/configure-ci.sh`: beide Schlüssel in `KNOWN_KEYS`, ein `case`-Block
analog zu `BACKEND_TEST_RUNNER` (`github` → `del_var`, `self-hosted` →
`set_var` mit `labels_to_json`, sonst `die`), plus dieselbe
Labels-ohne-self-hosted-Warnung.

### C. `bootstrap-ci-runner.sh`

1. **Node-Image vorab pullen**, analog zum bestehenden `TEST_IMAGE`-Pull —
   vermeidet ein Pull-Race, wenn beide Instanzen gleichzeitig starten.
2. **Mehrfachinstanzen ermöglichen.** `RUNNER_NAME` ist bereits über `--name`
   parametrisiert, aber `RUNNER_DIR="${RUNNER_HOME}/runner"` ist festverdrahtet
   — jede Instanz braucht ein eigenes Verzeichnis. `RUNNER_DIR` aus dem
   Instanznamen ableiten (oder `--dir` ergänzen). `svc.sh install` erzeugt den
   Unit-Namen bereits aus `RUNNER_NAME`, ist also schon eindeutig.
3. Die Self-Tests laufen pro Instanz unverändert.

Beide Instanzen teilen sich `ci-runner` und damit denselben rootless-Podman-Store.
Nebenläufige Container sind unproblematisch; das Vorab-Pullen entschärft den
einzigen Race beim ersten Lauf. Linger und `podman system migrate` sind
userweit und bereits abgedeckt.

### D. `.claude/rules/ci-cd-security.md`

- Layer-2-Tabelle: `frontend-build` von `ubuntu-latest` auf dieselbe
  Runner-/Gate-Beschreibung wie `backend-tests` umstellen.
- „Repo Settings to Verify": Runner-Zeile auf **zwei** Sandbox-Instanzen
  erweitern.
- Fork-Abschnitt um `FRONTEND_BUILD_RUNNER` ergänzen.

Die Reviewer-Checkliste braucht keine neue Zeile — „Does a workflow on
`ci-sandbox` run `pip install`, `npm install`, or any untrusted code directly
on the runner host (not inside `podman run`)?" deckt den Fall bereits ab.

## Reihenfolge (wichtig)

1. **PR #420 muss zuerst gemergt sein.** Er dokumentiert das scharfgeschaltete
   `ci-tests`-Gate. Die Settings selbst sind bereits live, aber ohne #420
   widerspricht die Doku dem Zustand.
2. Bootstrap-Änderung + zweite Instanz auf BaluNode einrichten und
   `gh api repos/Xveyn/BaluHost/actions/runners` prüfen: zwei Runner mit Label
   `ci-sandbox`, beide `online`.
3. Erst dann `ci-check.yml` umstellen.

Reihenfolge 3-vor-2 würde die CI ausbremsen, ohne dass jemand merkt warum.

## Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Serialisierung halbiert den Durchsatz | zweite Instanz **vor** der Workflow-Änderung |
| `npm ci` ohne Cache spürbar langsamer | bewusst akzeptiert; reale Laufzeit nach dem ersten Lauf gegen 4m46s prüfen |
| Job-Umbenennung bricht Branch Protection | Job-ID bleibt `frontend-build`; nach dem Merge `gh api …/branches/main/protection` gegenprüfen |
| Freigabepflicht wird als CI-Hänger fehlgedeutet | im PR-Body benennen: PRs pausieren jetzt sichtbar auf „Review pending deployments" |
| Bösartiger Fork-PR löscht seine eigene `environment:`-Zeile | Fork-Policy `all_external_contributors` greift vorher — sie ist Repo-State, nicht PR-editierbar |
| Zweite Instanz erbt Isolationsfehler | die Bootstrap-Self-Tests müssen für **beide** Instanzen grün sein |
| Plattenverbrauch durch zwei `node_modules` + Images | `--rm` räumt Container ab; Workspaces liegen pro Instanz getrennt. Bei Bedarf `podman system prune` per Timer |

## Offen (bewusst nicht entschieden)

Ob Playwright später nachzieht, bleibt offen — der Job bräuchte Browser-Deps im
Image und ist deutlich schwerer. Erst nach Messung der realen Laufzeiten
sinnvoll zu beurteilen.
