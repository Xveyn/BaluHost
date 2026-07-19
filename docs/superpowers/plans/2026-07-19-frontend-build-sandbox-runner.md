# frontend-build → ci-sandbox Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `frontend-build` läuft PR-getriggert auf dem gehärteten `ci-sandbox`-Runner (BaluNode) hinter dem `ci-tests`-Freigabe-Gate, in rootless Podman — plus eine zweite Runner-Instanz gegen Serialisierung und eine neue `docs/CI.md` mit den Design-Entscheidungen.

**Architecture:** Spiegelt exakt das `backend-tests`-Muster in `ci-check.yml`: hartkodierte Upstream-Runner-Wahl, `vars.FRONTEND_BUILD_RUNNER` für Forks, Identity-Tripwire, aller untrusted Code in **einem** `podman run` gegen `docker.io/library/node:20-slim`. Spec: `docs/superpowers/specs/2026-07-19-frontend-build-sandbox-runner-design.md`.

**Tech Stack:** GitHub Actions, bash, rootless Podman, node:20-slim.

## Global Constraints

- **Reihenfolge ist Teil der Korrektheit:** Tasks 1–5 sind Branch-Arbeit. Task 6 (Operator, BaluNode) MUSS abgeschlossen sein, **bevor** der PR in Task 7 geöffnet wird — der PR-eigene CI-Lauf führt bereits die neue Workflow-Datei aus (`pull_request` nimmt die Workflow-Definition aus dem PR-Merge-Ref) und braucht daher schon den zweiten Runner und das gepullte Node-Image.
- PR #420 (ci-tests-Gate-Doku) muss vor dem Merge dieses PRs gemergt sein.
- Job-ID bleibt exakt `frontend-build` (Required-Status-Check auf `main`).
- Podman-Aufruf mit `--cpus=4 --memory=3g` (Box ist Prod-NAS + Gaming-PC).
- Kein npm-Cache, kein `actions/setup-node`, kein git im Container (Spec-Entscheidungen 1–3; `__GIT_COMMIT__`='unknown' ist akzeptiert und dokumentiert).
- `$GITHUB_STEP_SUMMARY`-Umleitung passiert auf dem HOST (Backend-Muster) — der Container schreibt nur stdout.
- Upstream-Verhalten hartkodiert über `github.repository == 'Xveyn/BaluHost'`; Fork-Wahl NUR über `vars.*`. actionlint-Warnungen „Context access might be invalid: FRONTEND_BUILD_RUNNER" sind erwartet (Variable upstream ungesetzt), analog zu den `ENABLE_*`-Warnungen.
- Shell auf der Dev-Maschine ist PowerShell 5.1 (kein `&&`); Bash-Tool für POSIX. Skript-Syntaxprüfung: `bash -n <script>`.
- Commit-Trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Branch: `feat/frontend-build-sandbox-runner` (existiert, enthält den Spec).

---

### Task 1: `ci-check.yml` — frontend-build auf Sandbox-Muster umstellen

**Files:**
- Modify: `.github/workflows/ci-check.yml` (der komplette `frontend-build:`-Job)
- Referenz (nur lesen): derselbe File, `backend-tests:`-Job — Tripwire-Step und Podman-Muster von dort spiegeln

**Interfaces:**
- Produces: Job `frontend-build` mit identischer Job-ID; für Task 2 die Variablennamen `FRONTEND_BUILD_RUNNER` (JSON-Array-String, z. B. `["self-hosted","my-box"]`).

- [ ] **Step 1: Job ersetzen**

Den bestehenden `frontend-build:`-Block vollständig ersetzen durch:

```yaml
  frontend-build:
    # Runner selection (#207-Muster, wie backend-tests): upstream IMMER der
    # gehärtete ci-sandbox-Runner (nicht konfigurierbar); Forks wählen über
    # die Repo-Variable FRONTEND_BUILD_RUNNER (JSON-Array, gesetzt von
    # scripts/configure-ci.sh), Fallback secret-freie ubuntu-latest-VM.
    # PR-Code kann das nicht beeinflussen: Repository-Literal + vars only.
    runs-on: ${{ fromJSON(github.repository == 'Xveyn/BaluHost' && '["self-hosted","ci-sandbox"]' || vars.FRONTEND_BUILD_RUNNER || '"ubuntu-latest"') }}
    # ci-tests-Freigabe-Gate: immer für Upstream-PRs; in Forks nur, wenn der
    # Fork einen self-hosted Runner gewählt hat. workflow_call (aus
    # deploy-production nach Merge) läuft ungegated — Code ist dann vertraut.
    environment: ${{ (github.event_name == 'pull_request' && (github.repository == 'Xveyn/BaluHost' || contains(vars.FRONTEND_BUILD_RUNNER, 'self-hosted'))) && 'ci-tests' || '' }}
    timeout-minutes: 15

    steps:
      - uses: actions/checkout@v5

      - name: Assert runner identity (defense-in-depth tripwire)
        # Upstream-only: identisch zum backend-tests-Tripwire.
        if: github.repository == 'Xveyn/BaluHost'
        run: |
          set -euo pipefail
          test "$(whoami)" = "ci-runner" || { echo "::error::Runner not running as ci-runner (got: $(whoami))"; exit 1; }
          test "$(id -u)" -ne 0 || { echo "::error::Runner running as root"; exit 1; }
          command -v podman >/dev/null || { echo "::error::podman not installed on runner host"; exit 1; }
          for grp in docker sudo wheel; do
            if id -nG "$(whoami)" | tr ' ' '\n' | grep -qx "$grp"; then
              echo "::error::ci-runner is in group '$grp' — isolation broken"
              exit 1
            fi
          done
          echo "Identity OK: $(whoami) uid=$(id -u) groups=$(id -nG)"

      - name: Lint + build + unit tests (with coverage) in rootless Podman container
        env:
          NODE_IMAGE: docker.io/library/node:20-slim
        run: |
          set -euo pipefail
          # Kein npm-Cache: ein PR-beschreibbarer Cache wäre geteilter Zustand
          # zwischen PRs (Poisoning). npm ci läuft frisch, wie pip install im
          # backend-tests-Job. --cpus/--memory: die Box ist zugleich Prod-NAS;
          # CI darf sie nicht sättigen. Kein git im Image: vite.config.ts
          # fällt auf __GIT_COMMIT__='unknown'/buildType 'release' zurück —
          # akzeptiert, der Gate-Build wird verworfen (Deploy baut auf
          # BaluNode mit git). Details: docs/CI.md.
          # --maxWorkers=4: --cpus ist eine CFS-Quote, KEIN cpuset — os.cpus()
          # im Container meldet weiterhin alle 12 Host-Threads, Vitest würde
          # also ~11 jsdom-Worker in die 3-GB-Grenze spawnen (OOM-Kill).
          podman run --rm \
            --network=bridge \
            --cpus=4 --memory=3g \
            -v "${{ github.workspace }}:/work:Z" \
            -w /work/client \
            "$NODE_IMAGE" \
            bash -c "set -euo pipefail; npm ci && npx eslint . && npm run build && npm run test:coverage -- --maxWorkers=4"

      - name: Frontend coverage → job summary
        if: always()
        env:
          NODE_IMAGE: docker.io/library/node:20-slim
        run: |
          set -euo pipefail
          if [ ! -f client/coverage/coverage-summary.json ]; then
            echo "no client/coverage/coverage-summary.json — skipping coverage summary"
            exit 0
          fi
          # Parsen im selben gepinnten Image (nur stdlib, kein npm install).
          # Der Container schreibt nach stdout; die Umleitung in
          # $GITHUB_STEP_SUMMARY passiert auf dem HOST — die Variable ist ein
          # Host-Pfad und existiert im Container nicht.
          podman run --rm \
            -v "${{ github.workspace }}:/work:Z" \
            -w /work/client \
            "$NODE_IMAGE" \
            node -e '
              const fs = require("fs");
              const t = JSON.parse(fs.readFileSync("coverage/coverage-summary.json", "utf8")).total;
              const row = (k) => `| ${k} | ${t[k].pct}% (${t[k].covered}/${t[k].total}) |`;
              process.stdout.write(["## Frontend coverage (client)", "", "| Metric | Coverage |", "|---|---|", row("lines"), row("statements"), row("functions"), row("branches"), ""].join("\n") + "\n");
            ' \
            >> "$GITHUB_STEP_SUMMARY"
```

Wichtige Deltas zum Original, die NICHT verloren gehen dürfen: `actions/setup-node` entfällt ersatzlos; das alte `node -e` nutzte `fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, …)` — im Container ist diese Env leer, deshalb stdout + Host-Redirect; der `if (!fs.existsSync(p)) process.exit(0)`-Guard wandert als `[ ! -f … ]` auf den Host (spart den Container-Start komplett).

- [ ] **Step 2: backend-tests dieselbe Kappung geben (Spec, Abschnitt A)**

Im `backend-tests`-Job desselben Files, am bestehenden `podman run` (Zeile ~64): `--cpus=4 --memory=3g` ergänzen **und** im inneren pytest-Aufruf `-n auto` durch `-n 4` ersetzen — aus demselben Grund wie oben: `-n auto` zählt die 12 Host-Threads, nicht die CFS-Quote. Sonst NICHTS an dem Job ändern (kein Umbau des Tripwires, der Env-Zeilen oder der Coverage-Schritte).

- [ ] **Step 3: Verifizieren**

Run: `bash -n` ist für YAML nutzlos — stattdessen: `npx --yes actionlint@latest .github/workflows/ci-check.yml 2>&1 | head -30` (falls Netz/npx verfügbar; sonst `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci-check.yml'))"` als Minimal-Syntaxcheck).
Expected: keine neuen Fehler; Warnungen „Context access might be invalid: FRONTEND_BUILD_RUNNER" sind erwartet und OK.

- [ ] **Step 4: Diff-Selbstkontrolle** — `git diff .github/workflows/ci-check.yml`: am `backend-tests`-Job NUR die zwei Kappungs-Änderungen (podman-Flags + `-n 4`), Job-ID `frontend-build` unverändert, keine anderen Jobs berührt.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci-check.yml
git commit -m "ci(frontend): run frontend-build in rootless podman on ci-sandbox; cap CI container resources"
```

---

### Task 2: Fork-Konfiguration (`ci-config.example.conf` + `configure-ci.sh`)

**Files:**
- Modify: `ci-config.example.conf` (nach dem `BACKEND_TEST_RUNNER_LABELS`-Block)
- Modify: `scripts/configure-ci.sh:46-48` (`KNOWN_KEYS`) und nach `:113` (neuer case-Block)
- Prüfen/ggf. Modify: `docs/deployment/SELF_HOSTING.en.md` (falls dort `BACKEND_TEST_RUNNER` dokumentiert ist, `FRONTEND_BUILD_RUNNER` analog ergänzen)

**Interfaces:**
- Consumes: Variablennamen aus Task 1.
- Produces: Config-Keys `FRONTEND_BUILD_RUNNER` (`github`|`self-hosted`, Default `github`) und `FRONTEND_BUILD_RUNNER_LABELS` (CSV).

- [ ] **Step 1: `ci-config.example.conf` ergänzen** — direkt unter dem `#BACKEND_TEST_RUNNER_LABELS=…`-Block:

```
# Where the frontend build+tests run: 'github' (default, ubuntu-latest VM) or 'self-hosted'
FRONTEND_BUILD_RUNNER=github

# Extra labels of your self-hosted runner (comma-separated).
# Only used with FRONTEND_BUILD_RUNNER=self-hosted. 'self-hosted' is always implied.
#FRONTEND_BUILD_RUNNER_LABELS=my-test-box
```

Zusätzlich im Kopfkommentar der Datei (nach der Zeile mit `docs/deployment/SELF_HOSTING.en.md`) den Verweis ergänzen: `# CI design decisions (runners, gates, caching): docs/CI.md`

- [ ] **Step 2: `configure-ci.sh` erweitern**

`KNOWN_KEYS` (Zeile 46–48): `FRONTEND_BUILD_RUNNER FRONTEND_BUILD_RUNNER_LABELS` in die Liste aufnehmen.

Nach dem `BACKEND_TEST_RUNNER`-Block (nach Zeile 113) einfügen:

```bash
case "${CFG[FRONTEND_BUILD_RUNNER]:-github}" in
    github)      del_var FRONTEND_BUILD_RUNNER ;;
    self-hosted) set_var FRONTEND_BUILD_RUNNER "$(labels_to_json "${CFG[FRONTEND_BUILD_RUNNER_LABELS]:-}")" ;;
    *) die "FRONTEND_BUILD_RUNNER must be 'github' or 'self-hosted'" ;;
esac
if [[ "${CFG[FRONTEND_BUILD_RUNNER]:-github}" != "self-hosted" && -n "${CFG[FRONTEND_BUILD_RUNNER_LABELS]:-}" ]]; then
    echo "WARNING: FRONTEND_BUILD_RUNNER_LABELS is set but FRONTEND_BUILD_RUNNER is not 'self-hosted' — labels ignored" >&2
fi
```

- [ ] **Step 3: Verifizieren**

Run: `bash -n scripts/configure-ci.sh` — Expected: kein Output.
Run (Dry-Run-Funktionstest im Scratchpad, NICHT im Repo):

```bash
cd "$(mktemp -d)" || exit 1
printf 'FRONTEND_BUILD_RUNNER=self-hosted\nFRONTEND_BUILD_RUNNER_LABELS=my-box\n' > ci-config.conf
bash "/d/Programme (x86)/Baluhost/scripts/configure-ci.sh" --repo someone/BaluHost --dry-run
```

Expected: `[dry-run] gh variable set FRONTEND_BUILD_RUNNER … '["self-hosted","my-box"]'` — und mit `FRONTEND_BUILD_RUNNER=github` stattdessen die delete-Zeile. (Der `--repo`-Guard gegen Xveyn/BaluHost greift vor jedem echten API-Call; dry-run macht ohnehin keine.)

**Achtung, ungeprüfte Annahme:** Der Test unterstellt, dass das Skript `ci-config.conf` im CWD sucht. Prüfe zuerst die `CONFIG_FILE`-Auflösung am Skriptanfang (Zeilen 1–40); sucht es im Repo-Root oder relativ zum Skript, den Test dort mit einer temporären `ci-config.conf` fahren (Datei ist gitignored) und sie danach löschen — sie darf unter keinen Umständen committet werden.

- [ ] **Step 4: `SELF_HOSTING.en.md` prüfen** — per `Select-String -Path docs/deployment/SELF_HOSTING.en.md -Pattern "BACKEND_TEST_RUNNER"`. Bei Treffern den Frontend-Pendant-Absatz im selben Stil ergänzen; keine Treffer → nichts tun, im Report vermerken.

- [ ] **Step 5: Commit**

```bash
git add ci-config.example.conf scripts/configure-ci.sh docs/deployment/SELF_HOSTING.en.md
git commit -m "ci(fork-config): FRONTEND_BUILD_RUNNER variable + apply-script support"
```

---

### Task 3: `bootstrap-ci-runner.sh` — Mehrfachinstanzen + Node-Image

**Files:**
- Modify: `scripts/bootstrap-ci-runner.sh`

**Interfaces:**
- Produces: neuer Flag `--dir <name>` (Instanzverzeichnis-Name unter `$RUNNER_HOME`, Default `runner`); daraus abgeleitet `RUNNER_DIR` **und** `RUNNER_WORK`; Konstante `NODE_IMAGE`. Task 6 (Operator) verwendet exakt die im Header dokumentierten Kommandos.

- [ ] **Step 1: Instanz-Parametrisierung**

Die Zeilen 30–31 setzen `RUNNER_WORK`/`RUNNER_DIR` fest, **bevor** die Args geparst sind — beides muss NACH das Arg-Parsing wandern und vom neuen `--dir` abhängen:

```bash
# ---------- Configuration ---------- (Zeilen 30-31 ERSETZEN durch:)
RUNNER_DIR_NAME="runner"   # pro Instanz eindeutig; zweite Instanz: --dir runner-2

# ---------- Arg parsing ---------- (im case ergänzen:)
    --dir)   RUNNER_DIR_NAME="$2"; shift 2 ;;

# direkt NACH der while-Schleife (nach Zeile 51):
RUNNER_DIR="${RUNNER_HOME}/${RUNNER_DIR_NAME}"
RUNNER_WORK="${RUNNER_HOME}/_work-${RUNNER_DIR_NAME}"
```

**KORREKTUR (Task 3, verifiziert):** Die ursprüngliche Sorge, zwei Instanzen teilten sich `_work` und zerschössen sich den Checkout, war unbegründet — `config.sh` erhält `--work "_work"` **relativ zu `RUNNER_DIR`**, der effektive Work-Dir ist also `$RUNNER_DIR/_work` und die Instanz-Trennung kommt mit `--dir` automatisch. `RUNNER_WORK` ist vorbestehender toter Code (einziger Effekt: ein `mkdir`-Pre-Create eines nie benutzten Verzeichnisses). Konsequenz: `RUNNER_WORK` bleibt unverändert auf `${RUNNER_HOME}/_work` für alle Instanzen (kein per-Instanz-Suffix — das würde nur ein weiteres unbenutztes Verzeichnis erzeugen), plus ein Kommentar, der den realen Work-Dir dokumentiert. Der tote Code selbst ist ein Nebenbefund (Maintainer-Entscheidung, ggf. Issue).

- [ ] **Step 2: Node-Image vorab pullen** — bei den Konstanten `NODE_IMAGE="docker.io/library/node:20-slim"` ergänzen und neben dem bestehenden `as_runner podman pull "$TEST_IMAGE"` (Zeile ~169): `as_runner podman pull "$NODE_IMAGE"`. (Verhindert einen Pull-Race, wenn beide Instanzen gleichzeitig ihren ersten Job bekommen.)

- [ ] **Step 3: Header-Usage aktualisieren** — im Kopfkommentar dokumentieren:

```
# Usage:
#   sudo ./bootstrap-ci-runner.sh --token <RUNNER_REGISTRATION_TOKEN>
#   # zweite Instanz (parallele CI-Jobs; frontend-build + backend-tests):
#   sudo ./bootstrap-ci-runner.sh --token <TOKEN> --name BaluNode-ci-sandbox-2 --dir runner-2
```

und die Pre-Pull-Zeile im Beschreibungsblock um das Node-Image ergänzen.

- [ ] **Step 4: Verifizieren** — `bash -n scripts/bootstrap-ci-runner.sh` → kein Output. Zusätzlich per Read prüfen: keine verbliebene Verwendung von `RUNNER_DIR`/`RUNNER_WORK` VOR dem Arg-Parsing (sonst greift `--dir` nicht überall).

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap-ci-runner.sh
git commit -m "ci(bootstrap): multi-instance sandbox runners (--dir) + pre-pull node image"
```

---

### Task 4: `docs/CI.md` — Design-Entscheidungen (fork-/dev-facing)

**Files:**
- Create: `docs/CI.md`

**Interfaces:** referenziert von `ci-config.example.conf` (Task 2) und `ci-cd-security.md` (Task 5).

- [ ] **Step 1: Datei anlegen.** Zielgruppe: Forks und künftige Entwickler — **nicht** das interne Threat-Model (das bleibt in `.claude/rules/ci-cd-security.md`; `docs/CI.md` verlinkt darauf). Englisch (wie SELF_HOSTING.en.md). Gliederung mit verbindlichem Inhalt:

```markdown
# CI Design Decisions

Why the BaluHost pipeline is built the way it is. Fork setup: see
`ci-config.example.conf` + `scripts/configure-ci.sh`; the security threat
model lives in `.claude/rules/ci-cd-security.md`.

## Runner model
- Which jobs run where (table: job → upstream runner → fork variable → gate).
- Two-layer isolation of the ci-sandbox runner (unprivileged `ci-runner`
  user + rootless Podman; untrusted code NEVER runs on the runner host).
- Why upstream runner choice is hardcoded (`github.repository` literal):
  PR content must not be able to influence runner selection.
- Why there are two sandbox instances (one self-hosted runner = one job at
  a time; backend-tests + frontend-build would serialize).

## Approval gates
- `ci-tests` environment: PR-triggered jobs on self-hosted hardware pause
  for manual approval ("Review pending deployments"); one click approves
  all gated jobs of that run. `workflow_call` from the deploy pipeline is
  ungated (code already merged = trusted).
- Fork PR approval policy `all_external_contributors` and WHY it outranks
  the environment gate for forks (PRs execute the PR's own workflow file
  and can delete their `environment:` line; repo settings they cannot touch).

## Deliberate non-features
- **No dependency caches on self-hosted runners.** A PR-writable cache is
  shared mutable state between PRs (poisoning). `npm ci` / `pip install`
  run fresh per job inside the container.
- **No git in the node image.** `__GIT_COMMIT__` becomes 'unknown' in the
  CI gate build; the deployed frontend is built during deploy where git
  exists. Don't "fix" this by installing git.
- **mdadm tests never on self-hosted hardware** (loop-device tests on
  GitHub VMs only) — real mdadm can destroy disks.
- **Resource limits** (`--cpus`/`--memory`) on CI containers: the runner
  host is also the production NAS.

## Egress expectations
Containers need: registry.npmjs.org (npm), pypi.org +
files.pythonhosted.org (pip), docker.io (images), api.github.com.
Any future egress firewall must include all of these.
```

Jede Zeile inhaltlich gegen den realen Stand verifizieren (nicht abschreiben, nachsehen) — insbesondere die Job→Runner-Tabelle gegen die Workflow-Dateien.

- [ ] **Step 2: Commit**

```bash
git add docs/CI.md
git commit -m "docs(ci): add CI.md — runner model, gates, and deliberate non-features"
```

---

### Task 5: `.claude/rules/ci-cd-security.md` aktualisieren

**Files:**
- Modify: `.claude/rules/ci-cd-security.md`

- [ ] **Step 1: Vier Änderungen**

1. Layer-2-Tabelle, Zeile `ci-check.yml frontend-build`: von `ubuntu-latest` auf `**upstream: self-hosted, ci-sandbox (hardcoded); Forks: vars.FRONTEND_BUILD_RUNNER, Default ubuntu-latest** (rootless Podman everywhere)` und Trigger-Spalte um den `ci-tests`-Gate-Hinweis ergänzen — Formulierung exakt parallel zur `backend-tests`-Zeile.
2. „Repo Settings to Verify" → Runner-Zeile: zwei Sandbox-Instanzen (`BaluNode-ci-sandbox`, `BaluNode-ci-sandbox-2`) erwarten.
3. Fork-Configurability-Absatz (#207): `FRONTEND_BUILD_RUNNER` neben `BACKEND_TEST_RUNNER` nennen; die Gate-Bedingung zitiert dann beide `contains(vars.…)`-Ausdrücke.
4. Known Gap #8: in der künftigen Egress-Allowlist `registry.npmjs.org` ergänzen.

Zusätzlich am Ende des Layer-2-Abschnitts ein Verweis: „Fork-/Dev-facing Zusammenfassung der Design-Entscheidungen: `docs/CI.md`."

- [ ] **Step 2: Selbstkontrolle** — der `ci-tests`-Abschnitt (inkl. Incident-Notiz aus PR #420) sagt bisher „Gates PR-triggered **backend test** runs": auf „backend/frontend runs" erweitern. Danach `Select-String -Path .claude/rules/ci-cd-security.md -Pattern "ubuntu-latest.*frontend|frontend.*ubuntu-latest"` → keine widersprüchliche Restaussage.

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/ci-cd-security.md
git commit -m "docs(ci-security): frontend-build on ci-sandbox — layer table, runners, egress list"
```

---

### Task 6: OPERATOR-SCHRITT (Xveyn, auf BaluNode) — Smoke-Test + zweite Instanz

**KEIN Agent-Task.** Diese Kommandos führt Xveyn per SSH auf BaluNode aus, NACHDEM Tasks 1–5 auf dem Branch committet und gepusht sind. Der Controller wartet auf Bestätigung + Verifikation, bevor Task 7 startet.

- [ ] **Step 1: Branch auf die Box holen** (beliebiger Checkout-Pfad, NICHT /opt/baluhost):

```bash
git clone --depth 1 --branch feat/frontend-build-sandbox-runner https://github.com/Xveyn/BaluHost /tmp/balu-ci-branch
```

- [ ] **Step 2: Einmaliger Container-Smoke-Test als ci-runner** (belegt: keine nativen Deps fehlen, Build+Tests laufen im Image):

```bash
sudo -u ci-runner -H podman pull docker.io/library/node:20-slim
sudo cp -r /tmp/balu-ci-branch /var/lib/ci-runner/smoke && sudo chown -R ci-runner:ci-runner /var/lib/ci-runner/smoke
sudo -u ci-runner -H podman run --rm --network=bridge --cpus=4 --memory=3g \
  -v /var/lib/ci-runner/smoke:/work:Z -w /work/client \
  docker.io/library/node:20-slim \
  bash -c "set -euo pipefail; npm ci && npx eslint . && npm run build && npm run test:coverage -- --maxWorkers=4"
# Erwartung: eslint 0 Errors, build OK, Vitest-Suite grün (~1134 Tests).
# Laufzeit notieren (Vergleichswert: 4m46s auf ubuntu-latest).
sudo rm -rf /var/lib/ci-runner/smoke
```

- [ ] **Step 3: Registrierungs-Token holen** (am Dev-Rechner oder auf der Box, gh als Xveyn): `gh api -X POST repos/Xveyn/BaluHost/actions/runners/registration-token -q .token` — Token ist single-use, ~1 h gültig.

- [ ] **Step 4: Zweite Instanz registrieren** (mit dem Skript aus dem Clone von Step 1):

```bash
sudo /tmp/balu-ci-branch/scripts/bootstrap-ci-runner.sh --token <TOKEN> --name BaluNode-ci-sandbox-2 --dir runner-2
# Das Skript ist idempotent und läuft seine Self-Tests selbst; es MUSS mit
# "All self-tests passed" enden. Bricht es ab: Output an den Controller.
rm -rf /tmp/balu-ci-branch
```

- [ ] **Step 5: Verifikation (Dev-Rechner):**

```
gh api repos/Xveyn/BaluHost/actions/runners --jq '.runners[] | "\(.name)  \(.status)  [\([.labels[].name] | join(","))]"'
```

Expected: `BaluNode` (prod, online), `BaluNode-ci-sandbox` (online) **und** `BaluNode-ci-sandbox-2` (online), beide Sandbox-Instanzen mit Label `ci-sandbox`.

---

### Task 7: PR öffnen — der PR-Lauf ist der Live-Test

**Voraussetzungen:** Task 6 bestätigt (drei Runner online), PR #420 gemergt (sonst zuerst darauf hinweisen).

- [ ] **Step 1: Push + PR.** PR-Body (via Write-Tool + `--body-file`, Memory: keine Here-Strings) muss enthalten: Zusammenfassung der Umstellung; die drei Spec-Entscheidungen (kein Cache / eigene Fork-Variable / zweite Instanz) mit je einem Satz Begründung; Hinweis auf `docs/CI.md`; **explizit**: „PRs pausieren ab jetzt sichtbar auf ‚Review pending deployments' — das ist das ci-tests-Gate, kein Hänger; ein Klick gibt beide Jobs frei"; **und die DX-Änderung**: bisher lief `frontend-build` sofort und lieferte Lint-Feedback ohne Klick, während nur `backend-tests` wartete — künftig läuft vor der Freigabe gar nichts; Verweis auf Spec + PR #420.

- [ ] **Step 2: Den eigenen PR-Lauf beobachten** — er führt bereits die neue Workflow-Datei aus:
  1. Beide Jobs warten auf ci-tests-Freigabe → Xveyn klickt „Approve and deploy".
  2. `frontend-build` läuft auf `BaluNode-ci-sandbox`/`-2` (im Job-Log: „Runner name"), Tripwire grün, Podman-Step grün, Coverage-Summary erscheint im Run-Summary.
  3. `backend-tests` und `frontend-build` laufen **parallel** (Start-Zeitstempel vergleichen).
  4. Laufzeit `frontend-build` notieren und gegen 4m46s (ubuntu-latest) stellen.

- [ ] **Step 3: Branch-Protection-Gegenprobe:** `gh api repos/Xveyn/BaluHost/branches/main/protection --jq .required_status_checks.contexts` — `frontend-build` muss weiterhin matchen (Job-ID unverändert; der Check-Name bleibt gleich).

- [ ] **Step 4: Nach Merge:** ein `push: main` triggert `deploy-production` → `ci-check` via `workflow_call` läuft **ungegated** auf den Sandbox-Runnern durch (kein Approval-Stopp) und der Deploy wartet wie immer am `production`-Gate. Einmal beobachten und im Ledger festhalten.
