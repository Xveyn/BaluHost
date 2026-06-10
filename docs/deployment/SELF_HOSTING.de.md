# Self-Hosting & Fork-CI/CD

Diese Anleitung richtet sich an Entwickler, die BaluHost forken und (a) CI auf
ihrem Fork ausführen und (b) optional ihren Fork mit derselben Pipeline, die
das kanonische Repository verwendet, auf der eigenen Maschine deployen möchten.

> Das kanonische Repository (`Xveyn/BaluHost`) ignoriert diese gesamte
> Konfiguration — sein Pipeline-Verhalten ist in den Workflows fest kodiert und
> durch das Sicherheitsmodell in `.claude/rules/ci-cd-security.md` geschützt.

## Verhalten ohne Konfiguration

Ein frischer Fork funktioniert ohne jede Einrichtung:

| Workflow | Verhalten in Ihrem Fork |
|---|---|
| `ci-check` (Backend-Tests + Frontend-Build) | Läuft auf GitHub-gehosteten Runnern; Backend-Tests werden in einem rootless-Podman-Container auf `ubuntu-latest` ausgeführt |
| `playwright-e2e` (gemockt) | Läuft auf `ubuntu-latest` |
| `raid-mdadm-loopback` | Läuft auf `ubuntu-latest` (PRs, die RAID-Pfade berühren) |
| `tauri-build`, `tui-build` | Laufen auf `ubuntu-latest` (Push auf main / Tags) |
| `create-release` | Läuft bei Tag-Push (benötigt nur `GITHUB_TOKEN`) |
| `deploy-pi`, `release-stable` | Übersprungen (benötigen Secrets, die nicht vorhanden sind) |
| `deploy-production` | Inaktiv (actor-gated auf den Maintainer) |
| `deploy-fork` | Übersprungen bis zur Aktivierung (siehe unten) |

Hinweis: Ein direkter Push auf `main` des Forks löst `ci-check` nicht aus —
öffnen Sie einen PR innerhalb Ihres Forks, um CI auszuführen, oder aktivieren
Sie `deploy-fork` (das vor dem Deployment `ci-check` aufruft).

## Fork konfigurieren

1. Vorlage kopieren: `cp ci-config.example.conf ci-config.conf` (gitignored).
2. Werte anpassen — jeder Schlüssel ist in der Datei dokumentiert.
3. Anwenden: `scripts/configure-ci.sh` (erfordert eine authentifizierte
   [gh CLI](https://cli.github.com/); `--dry-run` zur Vorschau verwenden,
   `--repo <owner>/<repo>` für ein explizites Ziel).

Das Skript speichert die Einstellungen als GitHub-Repository-Variablen. Werte,
die dem Standard entsprechen, werden wieder entfernt — `gh variable list` zeigt
daher immer genau die Abweichungen vom Standardverhalten.

Die GitHub-Actions-Erweiterung der IDE meldet möglicherweise „Context access
might be invalid" für `vars.ENABLE_*` — das ist erwartetes Verhalten: nicht
gesetzte Variablen sind Teil des Designs (nicht gesetzt = Standardverhalten).

## Backend-Tests auf der eigenen Maschine ausführen

1. Einen [self-hosted Runner](https://docs.github.com/en/actions/hosting-your-own-runners)
   auf dem Fork registrieren und ihm ein Label geben, z. B. `my-test-box`.
   Podman muss auf dem Runner-Host installiert sein (Tests laufen in einem
   rootless Container).
2. In `ci-config.conf`: `BACKEND_TEST_RUNNER=self-hosted` und
   `BACKEND_TEST_RUNNER_LABELS=my-test-box` setzen, dann
   `scripts/configure-ci.sh` erneut ausführen.
3. **Sicherheit:** Mit einem konfigurierten self-hosted Test-Runner fordern
   PR-ausgelöste Testläufe im Fork die `ci-tests`-Umgebung an. GitHub legt
   diese beim ersten Einsatz ungeschützt an — wer jemals PRs von Fremden in
   seinen Fork akzeptiert, sollte sich als required reviewer für `ci-tests`
   unter Settings → Environments eintragen. Niemals PR-Code von nicht
   vertrauenswürdigen Personen auf wichtiger Hardware ausführen.

Die RAID-mdadm-Loopback-Tests sind die bewusste Ausnahme: Ihr Runner ist
**immer GitHub-gehostet** und lässt sich nicht konfigurieren. Echte
`mdadm`-Befehle könnten Datenträger auf einer physischen Maschine zerstören;
die Tests laufen ausschließlich auf ephemeren GitHub-VMs gegen Loop-Devices.

## Fork auf der eigenen Maschine deployen (`deploy-fork`)

Voraussetzungen (einmalig, auf einer Debian-Maschine):

1. BaluHost über den Installer installieren: siehe
   [DEPLOYMENT](DEPLOYMENT.de.md) und `deploy/install/install.sh`. Das
   Installationsverzeichnis notieren (Standard: `/opt/baluhost`).
2. Einen self-hosted Runner auf dem Fork **auf dieser Maschine** registrieren,
   mit einem Label nach Wahl, z. B. `my-prod-box`.
3. Empfohlen: unter Settings → Environments im Fork `fork-production` anlegen
   und sich selbst als required reviewer eintragen — jedes Deployment erfordert
   dann einen manuellen Klick, entsprechend dem Layer-4-Schutz des kanonischen
   Repositories.

Dann in `ci-config.conf`:

```
ENABLE_DEPLOY_FORK=true
DEPLOY_FORK_RUNNER_LABELS=my-prod-box
DEPLOY_FORK_INSTALL_DIR=/opt/baluhost
```

`scripts/configure-ci.sh` erneut ausführen. Ab sofort führt jeder Push auf
`main` des Forks `ci-check` aus und führt anschließend dasselbe
`deploy/scripts/ci-deploy.sh` aus, das auch das kanonische Produktions-
Deployment verwendet (Git-Update, Dependency-Sync, Build, Service-Neustart,
Health-Check, automatisches Rollback bei Fehler). Pre-Release-Tagging ist
kein Bestandteil von Fork-Deployments — das bleibt exklusiv der kanonischen
Pipeline vorbehalten.

## Fehlerbehebung

- **Ein Workflow schlägt mit „secret not found" fehl** — ein
  Secret-abhängiger Workflow (`ENABLE_DEPLOY_PI`, `ENABLE_RELEASE_STABLE`)
  wurde aktiviert, ohne das Secret zum Fork hinzuzufügen. Deaktivieren oder
  Secret ergänzen.
- **`backend-tests` hängt dauerhaft** — `BACKEND_TEST_RUNNER` zeigt auf
  Labels, zu denen kein Online-Runner existiert. Prüfen mit
  `gh api repos/<you>/<fork>/actions/runners`.
- **`deploy-fork` schlägt sofort fehl** — `ENABLE_DEPLOY_FORK=true` erfordert
  `DEPLOY_FORK_RUNNER_LABELS`; der Runner muss auf der Zielmaschine online sein
  und das Installationsverzeichnis eine abgeschlossene
  `deploy/install/install.sh`-Einrichtung enthalten.
- **PRs von Erstbeitragenden starten kein CI** — Standardverhalten von GitHub;
  den Lauf im Actions-Tab genehmigen („Approve and run").
