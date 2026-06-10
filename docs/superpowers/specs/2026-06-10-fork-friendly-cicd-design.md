# Design: Fork-/Self-Host-freundliche CI/CD (Issue #207)

**Datum:** 2026-06-10
**Issue:** #207 (Tracking-Epic aus Pipeline-Audit 2026-06-09)
**Scope:** Goal A (Contributor-CI) **und** Goal B (Self-Host-CD), inkl. B2-Legacy-Cleanup (nach Verifikation) und Doku.

## Ziel

Wer BaluHost forkt, soll die bestehende CI/CD-Pipeline selbst nutzen und per Config steuern können:

1. **Welche Workflows** in seinem Fork laufen (Toggles).
2. **Wo Backend-Tests laufen**: GitHub-hosted (`ubuntu-latest`, Default) oder eigener self-hosted Runner.
3. **Deploy auf eigene Infrastruktur** über einen neuen `deploy-fork`-Workflow, der denselben Deploy-Pfad (`ci-deploy.sh`) nutzt wie Produktion.

**Unverhandelbar:** Das 4-Layer-Sicherheitsmodell (`.claude/rules/ci-cd-security.md`) des kanonischen Repos wird nicht geschwächt. `deploy-production.yml` bleibt unverändert.

## Grundprinzip: Upstream hart verdrahtet, Forks config-getrieben

Das Verhalten des kanonischen Repos hängt **nicht** von Repository Variables ab, sondern wird hart an `github.repository == 'Xveyn/BaluHost'` gebunden. Damit ist das Upstream-Verhalten bit-identisch zu heute, unabhängig davon, ob/welche Vars gesetzt sind (keine Drift-, keine Fehlkonfigurationsgefahr). Forks steuern alles über Repository Variables (server-seitig, durch PR-Code nicht manipulierbar) mit fork-sicheren Defaults.

```
Upstream (Xveyn/BaluHost)        Fork (beliebig)
─────────────────────────        ───────────────────────────────
backend-tests: ci-sandbox,       backend-tests: ubuntu-latest
  Tripwire, ci-tests-Gate          oder eigener Runner (vars)
deploy-pi: an                    deploy-pi: aus (opt-in)
release-stable: an               release-stable: aus (opt-in)
deploy-production: aktiv         deploy-production: tot (Actor-Gate)
deploy-fork: tot (Repo-Guard)    deploy-fork: opt-in (vars)
```

## 1. Config-System

Drei Teile:

- **`ci-config.example.conf`** (Repo-Root, committed): dokumentiert alle Optionen mit Kommentaren und Defaults. Shell-Syntax `KEY=value` (gleiches Muster wie `deploy/install/install.conf`).
- **`ci-config.conf`** (lokal, in `.gitignore`): Kopie des Devs mit eigenen Werten. Wird nie committet → keine Diff-Pollution in PRs ans Upstream.
- **`scripts/configure-ci.sh`** (bash): liest die Conf, validiert Keys/Werte, setzt sie via `gh variable set` als Repository Variables auf dem Fork; löscht Vars, deren Wert dem Default entspricht (`gh variable delete`), damit der Var-Bestand minimal bleibt. Flags: `--repo <owner/repo>` (Default: `gh repo view`-Ermittlung), `--dry-run`. Voraussetzung: `gh` CLI authentifiziert; läuft unter Git-Bash/WSL/Linux/macOS.

### Config-Schlüssel → Repository Variables

| Conf-Key | Variable | Default (Var ungesetzt) |
|---|---|---|
| `BACKEND_TEST_RUNNER=github\|self-hosted` + `BACKEND_TEST_RUNNER_LABELS=<labels>` | `BACKEND_TEST_RUNNER` als JSON-Array-String, z. B. `["self-hosted","my-box"]` | `ubuntu-latest` |
| `ENABLE_PLAYWRIGHT_E2E=true\|false` | `ENABLE_PLAYWRIGHT_E2E` | **an** (`!= 'false'`) |
| `ENABLE_RAID_LOOPBACK=true\|false` | `ENABLE_RAID_LOOPBACK` | **an** (`!= 'false'`) |
| `ENABLE_TAURI_BUILD=true\|false` | `ENABLE_TAURI_BUILD` | **an** (`!= 'false'`) |
| `ENABLE_TUI_BUILD=true\|false` | `ENABLE_TUI_BUILD` | **an** (`!= 'false'`) |
| `ENABLE_DEPLOY_PI=true\|false` | `ENABLE_DEPLOY_PI` | **aus** (`== 'true'`) — secret-abhängig |
| `ENABLE_RELEASE_STABLE=true\|false` | `ENABLE_RELEASE_STABLE` | **aus** (`== 'true'`) — secret-abhängig |
| `ENABLE_DEPLOY_FORK=true\|false` | `ENABLE_DEPLOY_FORK` | **aus** (`== 'true'`) |
| `DEPLOY_FORK_RUNNER_LABELS=<labels>` | `DEPLOY_FORK_RUNNER` als JSON-Array-String | — (Pflicht bei `ENABLE_DEPLOY_FORK`) |
| `DEPLOY_FORK_INSTALL_DIR=<pfad>` | `DEPLOY_FORK_INSTALL_DIR` | `/opt/baluhost` |

Default-Logik: **secret-freie** Workflows sind per Default an (Zero-Config-Fork verhält sich wie heute, nur ohne Hänger/Fails), **secret-abhängige** sind per Default aus und überspringen sauber („skipped" statt rot).

Das kanonische Repo braucht **keine** Vars (Upstream-Verhalten ist hart verdrahtet, s. o.).

## 2. `ci-check.yml`-Umbau (A1 + A2)

```yaml
backend-tests:
  runs-on: ${{ fromJSON(github.repository == 'Xveyn/BaluHost' && '["self-hosted","ci-sandbox"]' || vars.BACKEND_TEST_RUNNER || '"ubuntu-latest"') }}
  environment: ${{ (github.event_name == 'pull_request' && (github.repository == 'Xveyn/BaluHost' || contains(vars.BACKEND_TEST_RUNNER, 'self-hosted'))) && 'ci-tests' || '' }}
```

- **Podman-Pfad bleibt für alle Runner identisch** — `ubuntu-latest`-Images haben Podman vorinstalliert. Ein Codepfad, Container-Isolation gilt überall.
- **Identity-Tripwire** (`whoami == ci-runner` etc.) läuft nur upstream: `if: github.repository == 'Xveyn/BaluHost'`. Fremde Runner (anderer Username) und GitHub-Runner skippen ihn.
- **`ci-tests`-Gate**: upstream immer bei PRs (wie heute); im Fork nur, wenn der Fork self-hosted testet. GitHub erstellt das Environment im Fork bei Erstnutzung ungeschützt — die Doku weist Fork-Owner an, Required Reviewers zu setzen, wenn sie Fremd-PRs auf ihrem Runner zulassen.
- **A2:** `development` aus Triggern von `ci-check.yml` (`branches: [main, development]`, `push: development`) und `deploy-pi.yml` entfernen; `master` aus `playwright-e2e.yml` entfernen.

## 3. Workflow-Toggles (Job-Level-Guards)

| Workflow | Guard auf dem Job |
|---|---|
| `playwright-e2e.yml` → `mock-e2e` | `vars.ENABLE_PLAYWRIGHT_E2E != 'false'` (zusätzlich zur bestehenden Bedingung) |
| `raid-mdadm-loopback.yml` | `vars.ENABLE_RAID_LOOPBACK != 'false'` |
| `tauri-build.yml` | `vars.ENABLE_TAURI_BUILD != 'false'` |
| `tui-build.yml` | `vars.ENABLE_TUI_BUILD != 'false'` |
| `deploy-pi.yml` | `github.repository == 'Xveyn/BaluHost' \|\| vars.ENABLE_DEPLOY_PI == 'true'` |
| `release-stable.yml` | `github.repository == 'Xveyn/BaluHost' \|\| vars.ENABLE_RELEASE_STABLE == 'true'` |

Ungeguarded bleiben: `frontend-build` (Kern-CI), `create-release` (tag-getrieben, nur `GITHUB_TOKEN`), `live-e2e` (bereits secret+environment-gated), `deploy-production` (Actor-Gate deckt Forks ab; Datei bleibt unangetastet).

Hinweis Upstream-Semantik: Im kanonischen Repo sind die `!= 'false'`-Toggles faktisch immer an (Vars dort ungesetzt); die `== 'true'`-Workflows sind durch den `github.repository`-Anteil hart an. Reguläre CI/CD upstream ist damit nicht abschaltbar — gewollt.

## 4. `deploy-fork.yml` (neu)

```yaml
name: Deploy Fork
on:
  push: { branches: [main] }
  workflow_dispatch:
    inputs:
      sync_permissions: { type: boolean, default: false }
concurrency: { group: fork-deploy, cancel-in-progress: false }
permissions: { contents: read }
jobs:
  ci-check:
    if: vars.ENABLE_DEPLOY_FORK == 'true' && github.repository != 'Xveyn/BaluHost'
    uses: ./.github/workflows/ci-check.yml
  deploy:
    needs: ci-check
    if: vars.ENABLE_DEPLOY_FORK == 'true' && github.repository != 'Xveyn/BaluHost'
    runs-on: ${{ fromJSON(vars.DEPLOY_FORK_RUNNER) }}
    environment: fork-production
    timeout-minutes: 30
    steps:
      - name: Run deploy script
        env:
          INSTALL_DIR: ${{ vars.DEPLOY_FORK_INSTALL_DIR || '/opt/baluhost' }}
          DEPLOY_ACTOR: ${{ github.actor }}
          SYNC_PERMISSIONS: ${{ inputs.sync_permissions == true && '1' || '0' }}
        run: |
          export GITHUB_ACTOR="$DEPLOY_ACTOR"
          "$INSTALL_DIR/deploy/scripts/ci-deploy.sh"
      - name: Show deploy state
        if: always()
        run: cat "${{ vars.DEPLOY_FORK_INSTALL_DIR || '/opt/baluhost' }}/.deploy-state" 2>/dev/null || echo "No deploy state file"
```

Entscheidungen:

- **Wiederverwendet `ci-deploy.sh` unverändert** — das Skript ist bereits vollständig `INSTALL_DIR`-parametrisiert (Default `/opt/baluhost`), enthält kein hartes `Xveyn`/`sven`. Ein getesteter Deploy-Pfad für Prod und Fork.
- **Kein Actor-Gate** (Fork-Owner regiert sein eigenes Repo). **Kein Pre-Release-Tagging** (braucht `DEPLOY_PAT`; Tagging bleibt exklusiv in `deploy-production.yml`).
- **Repo-Guard** `github.repository != 'Xveyn/BaluHost'` macht den Workflow im kanonischen Repo tot. Zusätzlich kommt `deploy-fork.yml` in CODEOWNERS.
- **Voraussetzungen** (in SELF_HOSTING dokumentiert): einmalig `deploy/install/install.sh` auf der Zielbox (Debian), self-hosted Runner mit eigenem Label registriert, `fork-production`-Environment optional mit Required Reviewers geschützt.

## 5. B2: Legacy-Cleanup (`User=sven`-Cluster)

**Status: Verifikation auf BaluNode ausstehend** (Entscheidungs-Gate, kein Blocker für Abschnitte 1–4).

Prüfkriterium auf BaluNode:

```bash
systemctl list-units 'baluhost-*' --all --no-pager
grep -l '/home/sven' /etc/systemd/system/*.service 2>/dev/null || echo "kein /home/sven in Units"
systemctl cat baluhost-backend | grep -E 'ExecStart|User=|WorkingDirectory'
```

- **Wenn tot** (laufende Units zeigen auf `/opt/baluhost`, kein `/home/sven` in `/etc/systemd/system`): löschen von `deploy/systemd/*.service` (5 Dateien), `deploy/scripts/install-systemd-services.sh`, `deploy/scripts/setup-production.sh`, `deploy/scripts/migrate-to-opt.sh`; `deploy/systemd/README.md` und Referenzen in Doku/Skripten bereinigen. `install-nginx-config.sh` einzeln prüfen (Pfad-Annahmen).
- **Wenn live**: nicht löschen; Design-Nachtrag zur Parametrisierung (separater Abschnitt, dann erneute Abnahme).

## 6. Doku

- **`docs/deployment/SELF_HOSTING.de.md` + `.en.md`** (neues Dokument, zweisprachig nach Repo-Muster): Fork einrichten → `ci-config.conf` aus `ci-config.example.conf` kopieren und ausfüllen → `scripts/configure-ci.sh` ausführen → optional eigenen Test-Runner registrieren → optional Self-Host-Deploy (`install.sh`, Runner-Label, `ENABLE_DEPLOY_FORK`, Environment-Schutz). Inkl. Tabelle aller Config-Keys und Troubleshooting (hängende/failende Workflows vor dieser Änderung).
- **`CONTRIBUTING.md`**: kurzer Abschnitt „CI in your fork" mit Verweis auf SELF_HOSTING.
- **`README.md`**: Link auf SELF_HOSTING.
- **`.claude/rules/ci-cd-security.md`**: Layer 2 um die vars-getriebene Runner-Wahl ergänzen (inkl. Begründung, warum Vars PR-sicher sind); `deploy-fork.yml` in die Workflow-Tabelle; Reviewer-Checklist erweitern: „Ändert eine Änderung die `github.repository == 'Xveyn/BaluHost'`-Bedingungen oder die `contains(vars.BACKEND_TEST_RUNNER, 'self-hosted')`-Gate-Logik?".
- **`.github/CODEOWNERS`**: `deploy-fork.yml` ist über `/.github/workflows/` bereits abgedeckt; `ci-config.example.conf` + `scripts/configure-ci.sh` aufnehmen.

## 7. Sicherheits-Leitplanken (Review-Kriterien für die Umsetzung)

1. Upstream-Verhalten ist **bit-identisch** zu heute: ci-sandbox-Runner, Identity-Tripwire, `ci-tests`-Gate bei PRs, Podman-Isolation, `deploy-production.yml` byte-identisch.
2. PR-Code kann weder Runner-Wahl noch Environment-Gates beeinflussen (Steuerung ausschließlich über `github.repository`-Literale und server-seitige Vars).
3. Kein Workflow erhält einen `pull_request`-/`pull_request_target`-Trigger auf self-hosted Runner.
4. `deploy-fork.yml` ist upstream tot (Repo-Guard) und CODEOWNERS-geschützt.
5. Keine neuen Secrets; `DEPLOY_PAT`/`BALUPI_DEPLOY_KEY` werden in keinen neuen Kontext exponiert.
6. Jede Workflow-Änderung gegen die Reviewer-Checklist in `ci-cd-security.md` prüfen.

## 8. Verifikation / Akzeptanztests

- **Statisch:** `actionlint` über alle Workflows; `configure-ci.sh --dry-run` mit Beispiel-Confs (leer, nur-CI, voll inkl. deploy-fork); shellcheck für `configure-ci.sh`.
- **Fork-Szenario (Goal A):** Test-Fork anlegen, Zero-Config prüfen: PR im Fork → `backend-tests` läuft grün auf `ubuntu-latest` (Podman-Pfad), `frontend-build` grün, `deploy-pi`/`release-stable` skipped, nichts hängt. Danach `configure-ci.sh` mit Toggles testen.
- **Fork-Szenario (Goal B):** mindestens Dry-Run-Niveau: `ENABLE_DEPLOY_FORK=true` + Runner-Label gesetzt → Workflow startet und ruft `ci-deploy.sh` auf (vollständiger Deploy-Test erfordert eine installierte Box; dokumentierter manueller Test).
- **Upstream-Regression:** No-op-PR ans kanonische Repo → `backend-tests` läuft wie bisher auf ci-sandbox mit `ci-tests`-Gate und Tripwire; Merge → `deploy-production` läuft unverändert.

## Offene Punkte

- B2-Verifikation auf BaluNode (Abschnitt 5) — Ergebnis entscheidet Löschen vs. Parametrisierungs-Nachtrag.
- Upstream muss Fork-PRs von Erst-Contributors weiterhin manuell freigeben („Approve and run") — unverändertes GitHub-Verhalten, wird in SELF_HOSTING erwähnt.
