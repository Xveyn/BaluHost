# Deploy rollt systemd-Units aus — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ci-deploy.sh` gleicht bei jedem Deploy die vier verwalteten systemd-Units mit ihren Repo-Templates ab, bricht bei einem kaputten Template mit Rollback ab und stellt im Rollback die alten Units wieder her.

**Architecture:** Ein neues Root-Skript `deploy/scripts/install-systemd-units.sh` rendert die Templates mit `process_template` aus `deploy/install/lib/common.sh`, prüft sie mit `systemd-analyze verify`, ersetzt nur abweichende Dateien atomar (mit Backup) und macht `daemon-reload` nur bei Änderung. `ci-deploy.sh` ruft es über einen ausgelagerten sudo-Kern (`sudo_repo_script`, Status 0/1/2) als Schritt 6b und im `rollback()` auf. Die Deploy-sudoers-Vorlage erlaubt genau dieses Skript.

**Tech Stack:** Bash (Debian 13, bash 5.2), systemd, pytest (Tests starten bash als Subprozess; laufen auch unter Git Bash auf Windows).

**Spec:** `docs/superpowers/specs/2026-09-27-deploy-renders-systemd-units-design.md`

## Global Constraints

- Verwaltete Units, exakt diese vier: `baluhost-backend`, `baluhost-scheduler`, `baluhost-webdav`, `baluhost-monitoring`. **Nicht** `baluhost-backend-local` (#717), **nicht** die Tray-User-Unit.
- Render-Werte wie Modul 10: `BALUHOST_USER`, `INSTALL_DIR`, `VENV_BIN="$INSTALL_DIR/backend/.venv/bin"`.
- `UNIT_BACKUP_DIR` Default `/var/backups/baluhost/units`, pro Unit bleiben die neuesten **10** Backups.
- `SYSTEMD_DIR` Default `/etc/systemd/system`.
- sudoers: genau zwei Zeilen (`/bin/bash` und `/usr/bin/bash` + `@@INSTALL_DIR@@/deploy/scripts/install-systemd-units.sh`), NOPASSWD, keine Argumente, keine Wildcards, kein `SETENV`.
- `sudo -n bash "$script"` steht in `ci-deploy.sh` weiterhin **genau einmal** (Vertrag aus `backend/tests/test_ci_deploy_permission_sync.py`).
- Die drei bestehenden Permission-Syncs (`run_permission_script`) bleiben rein warnend.
- Status-Kontrakt von `sudo_repo_script`: 0 = OK, 1 = Skript gescheitert, 2 = sudoers-Erlaubnis fehlt.
- Keine neuen Abhängigkeiten.
- Repo läuft mit `core.autocrlf=true`: Tests, die Shell-Dateien aus dem Repo ausführen, müssen sie mit `\n`-Zeilenenden in `tmp_path` kopieren.
- Commits enden mit `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Volle Backend-Suite gehört der CI; lokal laufen die in jedem Task genannten Testdateien.
- `backend/tests/test_ci_deploy_companion_cargo.py` hat unter Windows 3 vorbestehende Fehlschläge (auch auf unverändertem `main`, Plan-Review 2026-09-27) und steht deshalb in keiner lokalen Testliste; die CI prüft sie.

## Review Focus

1. **Zieldatei existiert noch nicht** (neu hinzugekommene Unit oder frische Box): Das Skript installiert sie ohne Backup und ohne an `cmp` zu scheitern. → Task 1, `test_leeres_zielverzeichnis_installiert_alle_units_ohne_backup`.
2. **Pfade mit Leerzeichen** (`INSTALL_DIR`, `SYSTEMD_DIR`, `UNIT_BACKUP_DIR`): Alle Expansionen sind gequotet, nichts zerfällt in Wörter. → Task 1, Fixture baut alle Verzeichnisse mit Leerzeichen im Namen.
3. **Zweiter Lauf direkt nach einem ersetzenden Lauf**: Er ist ein No-op ohne `daemon-reload`, sonst würde jeder Deploy die Units anfassen. → Task 1, `test_zweiter_lauf_ist_ein_noop`.
4. **Backup-Verzeichnis existiert noch nicht**: Es wird beim ersten Ersetzen angelegt. → Task 1, `test_eine_abweichende_unit_wird_ersetzt_mit_backup` (Fixture legt es nicht an).
5. **Manueller Aufruf mit `BALUHOST_USER`, während `User=` einen anderen Benutzer nennt**: Die Override hat Vorrang (nicht nur Rückfall). → Task 1, `test_benutzer_override_hat_vorrang`.

---

## File Structure

| Datei | Aktion | Verantwortung |
|---|---|---|
| `deploy/scripts/install-systemd-units.sh` | Create | Rendern, prüfen, ersetzen, neu laden (root) |
| `backend/tests/test_deploy_install_systemd_units.py` | Create | Verhaltenstests des Skripts, Paritätstest der Unit-Listen, sudoers-Test |
| `deploy/install/templates/baluhost-deploy-sudoers` | Modify | Zwei NOPASSWD-Zeilen für das Skript |
| `deploy/scripts/ci-deploy.sh` | Modify | `sudo_repo_script` + `warn_deploy_sudoers_missing` ausgelagert, Schritt 6b, Re-Render im Rollback, Kommentare 8c/Kopf |
| `backend/tests/test_ci_deploy_permission_sync.py` | Modify | Extraktor nimmt die ausgelagerten Funktionen mit |
| `backend/tests/test_ci_deploy_unit_sync.py` | Create | Status-Kontrakt `sudo_repo_script`, Lage von 6b, Rollback-Verdrahtung |
| `backend/app/services/unit_drift.py` | Modify | Docstring, Reparaturzeile zeigt auf das neue Skript |
| `backend/tests/services/test_unit_drift.py` | Modify | Reparaturzeilen-Test |
| `.claude/rules/ci-cd-security.md` | Modify | Known Gap 12 + Checklist „Sudoers / systemd" |

---

### Task 1: `install-systemd-units.sh` mit Verhaltenstests

**Files:**
- Create: `deploy/scripts/install-systemd-units.sh`
- Test: `backend/tests/test_deploy_install_systemd_units.py`

**Interfaces:**
- Consumes: `process_template <template> <output> KEY=VALUE…` und `log_error` aus `deploy/install/lib/common.sh` (unverändert).
- Produces: Skript unter festem Pfad, aufrufbar als `bash <INSTALL_DIR>/deploy/scripts/install-systemd-units.sh` ohne Argumente. stdout: je ersetzter Unit `CHANGED: <unit>`, am Ende `OK: all 4 units up to date`, `OK: all 4 units up to date, stale systemd state fixed by daemon-reload` oder `OK: <n> unit(s) replaced`. `daemon-reload` läuft, wenn etwas ersetzt wurde **oder** eine verwaltete Unit `NeedDaemonReload=yes` meldet. Exit 0 bei Erfolg, ≠ 0 bei jedem Fehler. Umgebung (nur Test/manuell): `SYSTEMD_DIR`, `UNIT_BACKUP_DIR`, `BALUHOST_UNITS_ALLOW_NONROOT=1`, `BALUHOST_USER`. Array im Skript: `UNITS=(baluhost-backend baluhost-scheduler baluhost-webdav baluhost-monitoring)` in genau dieser einzeiligen Form (Task 2 parst sie).

- [ ] **Step 1: Testdatei mit Harness und allen Verhaltenstests schreiben**

`backend/tests/test_deploy_install_systemd_units.py`:

```python
"""install-systemd-units.sh gleicht die Units mit ihren Templates ab (#689).

Das Skript laeuft hier wirklich unter bash, gegen einen nachgebauten
Installationsbaum in tmp_path. systemctl, systemd-analyze und id sind
Stub-Skripte vorn im PATH und protokollieren ihre Aufrufe. Jeder Pfad im
Baum enthaelt ein Leerzeichen: ein ungequotetes "$VAR" im Skript faellt hier
auf und nicht erst auf einer Box mit ungewoehnlichem Installationspfad.

Warum Verhalten statt Text: Der Test zu #689 selbst (test_deploy_proxy_headers)
las nur den Template-Text und blieb gruen, waehrend die Box ungeschuetzt lief.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "deploy" / "scripts" / "install-systemd-units.sh"
COMMON = REPO / "deploy" / "install" / "lib" / "common.sh"
TEMPLATES = REPO / "deploy" / "install" / "templates"
UNITS = ("baluhost-backend", "baluhost-scheduler", "baluhost-webdav", "baluhost-monitoring")
BASH = shutil.which("bash")

_STUB_SYSTEMCTL = """#!/bin/bash
echo "systemctl $*" >> "$FAKE_LOG"
if [[ "$1" == "show" && "$*" == *NeedDaemonReload* ]]; then echo "${FAKE_NEED_RELOAD:-no}"; exit 0; fi
if [[ "$1" == "show" ]]; then echo "${FAKE_USER-sven}"; exit 0; fi
if [[ "$1" == "daemon-reload" ]]; then exit "${FAKE_RELOAD_RC:-0}"; fi
exit 0
"""

_STUB_ANALYZE = """#!/bin/bash
echo "systemd-analyze $*" >> "$FAKE_LOG"
if [[ -n "${FAKE_VERIFY_FAIL:-}" ]]; then
    echo "$FAKE_VERIFY_FAIL: Unit has a bad unit file setting." >&2
    exit 1
fi
exit 0
"""

# Nur `id -u <name>` wird nachgebaut; alles andere geht an das echte id.
_STUB_ID = """#!/bin/bash
if [[ "${1:-}" == "-u" && -n "${2:-}" ]]; then
    if [[ "$2" == "sven" ]]; then echo 1000; exit 0; fi
    echo "id: '$2': no such user" >&2; exit 1
fi
exec /usr/bin/id "$@"
"""


def _copy_lf(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")


class Box:
    """Nachgebauter Installationsbaum plus Zielverzeichnisse, alle mit Leerzeichen."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path / "inst dir"
        self.script = self.root / "deploy" / "scripts" / "install-systemd-units.sh"
        self.templates = self.root / "deploy" / "install" / "templates"
        self.systemd = tmp_path / "etc systemd"
        self.backups = tmp_path / "var backups" / "units"  # bewusst NICHT angelegt
        self.stubs = tmp_path / "stub bin"
        self.log = tmp_path / "calls.log"

        _copy_lf(SCRIPT, self.script)
        _copy_lf(COMMON, self.root / "deploy" / "install" / "lib" / "common.sh")
        for unit in UNITS:
            _copy_lf(TEMPLATES / f"{unit}.service", self.templates / f"{unit}.service")
        self.systemd.mkdir()
        self.stubs.mkdir()
        for name, body in (("systemctl", _STUB_SYSTEMCTL),
                           ("systemd-analyze", _STUB_ANALYZE), ("id", _STUB_ID)):
            stub = self.stubs / name
            stub.write_text(body, encoding="utf-8", newline="\n")
            stub.chmod(0o755)
        self.log.write_text("", encoding="utf-8")

    def run(self, allow_nonroot: bool = True, **env: str) -> subprocess.CompletedProcess:
        full = {
            "PATH": "/usr/bin:/bin",
            "STUB_DIR": self.stubs.as_posix(),
            "SCRIPT_PATH": self.script.as_posix(),
            "FAKE_LOG": self.log.as_posix(),
            "SYSTEMD_DIR": self.systemd.as_posix(),
            "UNIT_BACKUP_DIR": self.backups.as_posix(),
        }
        if allow_nonroot:
            full["BALUHOST_UNITS_ALLOW_NONROOT"] = "1"
        full.update(env)
        # Den Stub-Pfad in bash selbst voranstellen: unter Git Bash ist
        # tmp_path "C:/…", und der Doppelpunkt zerlegte einen PATH-Eintrag.
        # `cd … && pwd` liefert die POSIX-Form (/c/…), unter Linux denselben Pfad.
        harness = 'export PATH="$(cd "$STUB_DIR" && pwd):$PATH"; exec bash "$SCRIPT_PATH"'
        return subprocess.run([BASH, "-c", harness], capture_output=True, text=True,
                              env=full, timeout=60)

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()

    def reloads(self) -> int:
        return sum(1 for c in self.calls() if c == "systemctl daemon-reload")

    def installed(self, unit: str) -> Path:
        return self.systemd / f"{unit}.service"

    def backups_of(self, unit: str) -> list[Path]:
        if not self.backups.exists():
            return []
        return sorted(p for p in self.backups.iterdir() if p.name.startswith(f"{unit}.service."))


@pytest.fixture
def box(tmp_path):
    if BASH is None:
        pytest.skip("bash nicht verfuegbar")
    return Box(tmp_path)


def _in_sync(box: Box) -> None:
    first = box.run()
    assert first.returncode == 0, first.stderr
    box.log.write_text("", encoding="utf-8")


# ─── Normalfaelle ────────────────────────────────────────────────────


def test_leeres_zielverzeichnis_installiert_alle_units_ohne_backup(box):
    result = box.run()

    assert result.returncode == 0, result.stderr
    for unit in UNITS:
        assert box.installed(unit).is_file()
        assert f"CHANGED: {unit}" in result.stdout
        assert box.backups_of(unit) == [], "ohne alte Datei gibt es nichts zu sichern"
    assert "OK: 4 unit(s) replaced" in result.stdout
    assert box.reloads() == 1


def test_zweiter_lauf_ist_ein_noop(box):
    _in_sync(box)
    before = {u: box.installed(u).stat().st_mtime_ns for u in UNITS}

    result = box.run()

    assert result.returncode == 0, result.stderr
    assert "CHANGED" not in result.stdout
    assert "OK: all 4 units up to date" in result.stdout
    assert box.reloads() == 0
    assert {u: box.installed(u).stat().st_mtime_ns for u in UNITS} == before


def test_gleiche_dateien_aber_systemd_veraltet_laedt_trotzdem_neu(box):
    """Der Fall nach einem gescheiterten daemon-reload: die Dateien stimmen
    schon, systemd faehrt aber noch die alte Fassung (NeedDaemonReload=yes).
    Ein erneuter Aufruf -- genau das, was die Reparaturzeile des Drift-Checks
    empfiehlt -- muss das beheben, statt 'up to date' zu melden."""
    _in_sync(box)

    result = box.run(FAKE_NEED_RELOAD="yes")

    assert result.returncode == 0, result.stderr
    assert "CHANGED" not in result.stdout
    assert box.reloads() == 1
    assert "daemon-reload" in result.stdout


def test_eine_abweichende_unit_wird_ersetzt_mit_backup(box):
    _in_sync(box)
    drifted = box.installed("baluhost-webdav")
    drifted.write_text(drifted.read_text(encoding="utf-8") + "# drift\n",
                       encoding="utf-8", newline="\n")
    others = {u: box.installed(u).stat().st_mtime_ns for u in UNITS if u != "baluhost-webdav"}

    result = box.run()

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("CHANGED:") == 1
    assert "CHANGED: baluhost-webdav" in result.stdout
    assert "# drift" not in drifted.read_text(encoding="utf-8")
    backups = box.backups_of("baluhost-webdav")
    assert len(backups) == 1
    assert "# drift" in backups[0].read_text(encoding="utf-8")
    assert box.reloads() == 1
    assert {u: box.installed(u).stat().st_mtime_ns for u in others} == others
    assert not list(box.systemd.glob(".*.new")), "keine Temp-Datei darf liegen bleiben"


def test_gerenderte_unit_ist_byte_gleich_mit_process_template(box):
    """Dieselbe Funktion und dieselben drei Werte wie Modul 10 — sonst liefen
    Installer und Deploy auseinander."""
    assert box.run().returncode == 0
    reference = box.root.parent / "reference.service"
    snippet = (
        'source "$COMMON"; root="$(cd "$ROOT" && pwd)"; '
        'process_template "$TPL" "$OUT" BALUHOST_USER=sven '
        '"INSTALL_DIR=$root" "VENV_BIN=$root/backend/.venv/bin"'
    )
    subprocess.run(
        [BASH, "-c", snippet], check=True, timeout=30,
        env={"PATH": "/usr/bin:/bin",
             "COMMON": (box.root / "deploy" / "install" / "lib" / "common.sh").as_posix(),
             "ROOT": box.root.as_posix(),
             "TPL": (box.templates / "baluhost-backend.service").as_posix(),
             "OUT": reference.as_posix()},
    )

    installed = box.installed("baluhost-backend").read_bytes()
    assert installed == reference.read_bytes()
    text = installed.decode("utf-8")
    assert "User=sven" in text
    assert "--proxy-headers" in text
    assert "@@" not in text


def test_benutzer_override_hat_vorrang(box):
    """systemctl meldet einen anderen (unbekannten) Benutzer: nur wenn die
    Override wirklich Vorrang hat, kommt User=sven heraus -- ein blosser
    Rueckfall auf BALUHOST_USER bestuende diesen Test nicht."""
    result = box.run(FAKE_USER="ghost", BALUHOST_USER="sven")

    assert result.returncode == 0, result.stderr
    assert "User=sven" in box.installed("baluhost-backend").read_text(encoding="utf-8")


def test_backup_rotation_behaelt_die_neuesten_zehn(box):
    _in_sync(box)
    target = box.installed("baluhost-backend")
    for i in range(12):
        target.write_text(f"# drift {i}\n", encoding="utf-8", newline="\n")
        result = box.run()
        assert result.returncode == 0, result.stderr

    backups = box.backups_of("baluhost-backend")
    assert len(backups) == 10
    assert backups[-1].read_text(encoding="utf-8") == "# drift 11\n"
    assert backups[0].read_text(encoding="utf-8") == "# drift 2\n"


# ─── Fehlerfaelle: nichts schreiben, Exit != 0 ───────────────────────


def test_verify_fehler_schreibt_nichts(box):
    _in_sync(box)
    drifted = box.installed("baluhost-webdav")
    drifted.write_text("# drift\n", encoding="utf-8", newline="\n")

    result = box.run(FAKE_VERIFY_FAIL="baluhost-webdav.service")

    assert result.returncode != 0
    assert "bad unit file setting" in result.stderr
    assert drifted.read_text(encoding="utf-8") == "# drift\n"
    assert box.backups_of("baluhost-webdav") == []
    assert box.reloads() == 0


def test_uebrig_gebliebener_platzhalter_bricht_ab(box):
    tpl = box.templates / "baluhost-monitoring.service"
    tpl.write_text(tpl.read_text(encoding="utf-8") + "Description=@@UNBEKANNT@@\n",
                   encoding="utf-8", newline="\n")

    result = box.run()

    assert result.returncode != 0
    assert "@@UNBEKANNT@@" in result.stderr
    assert list(box.systemd.iterdir()) == []


def test_leerer_dienstbenutzer_bricht_ab(box):
    result = box.run(FAKE_USER="")

    assert result.returncode != 0
    assert "BALUHOST_USER is unset" in result.stderr
    assert list(box.systemd.iterdir()) == []


def test_unbekannter_dienstbenutzer_bricht_ab(box):
    result = box.run(FAKE_USER="ghost")

    assert result.returncode != 0
    assert "ghost" in result.stderr
    assert list(box.systemd.iterdir()) == []


def test_gescheiterter_daemon_reload_ist_ein_fehler(box):
    result = box.run(FAKE_RELOAD_RC="1")

    assert result.returncode != 0
    assert "daemon-reload" in result.stderr


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="als root greift der Root-Check nicht")
def test_ohne_root_und_ohne_testnaht_bricht_ab(box):
    result = box.run(allow_nonroot=False)

    assert result.returncode != 0
    assert "must run as root" in result.stderr
    assert list(box.systemd.iterdir()) == []
```

- [ ] **Step 2: Tests laufen lassen, sie müssen scheitern**

Run: `cd backend; python -m pytest tests/test_deploy_install_systemd_units.py -v --no-cov -p no:cacheprovider`
Expected: alle Tests FAIL oder ERROR, weil `deploy/scripts/install-systemd-units.sh` nicht existiert (`FileNotFoundError` in `_copy_lf`).

- [ ] **Step 3: Skript schreiben**

`deploy/scripts/install-systemd-units.sh`:

```bash
#!/bin/bash
# Gleicht die systemd-Units von BaluHost mit ihren Repo-Templates ab (#689).
#
# Warum: ci-deploy.sh hat Unit-Dateien nie geschrieben -- das tat nur
# Installer-Modul 10, und das laeuft nur von Hand. Eine Template-Aenderung
# blieb deshalb unter <install-dir>/deploy/ liegen: --proxy-headers fehlte der
# laufenden Unit monatelang, und alle LAN-Gates waren wirkungslos. Jetzt ruft
# ci-deploy.sh dieses Skript bei jedem Deploy auf (Schritt 6b) und im Rollback
# noch einmal, dann mit den alten Templates.
#
# Ablauf:
#   1. rendern mit process_template aus deploy/install/lib/common.sh -- Byte
#      fuer Byte wie Modul 10, mit denselben drei Werten;
#   2. systemd-analyze verify ueber ALLE Units, bevor irgendetwas geschrieben
#      wird (gemessen auf BaluNode 2026-09-27: korrekte Units exit=0, relativer
#      ExecStart exit=1);
#   3. nur abweichende Dateien ersetzen: Backup, install in eine Temp-Datei im
#      Zielverzeichnis, atomarer mv;
#   4. daemon-reload nur, wenn sich etwas geaendert hat.
#
# Exit 0: alles im Takt oder erfolgreich ersetzt. Jeder andere Exit: ci-deploy
# rollt zurueck. Scheitert Schritt 1 oder 2, ist nichts geschrieben.
#
# Test-Naehte: SYSTEMD_DIR, UNIT_BACKUP_DIR und BALUHOST_UNITS_ALLOW_NONROOT
# sind aus der Umgebung ueberschreibbar. Ueber den Deploy erreicht keine davon
# das Skript: die sudoers-Zeile pinnt die Kommandozeile ohne SETENV, und sudo
# verwirft die Umgebung (env_reset). Wer die Umgebung eines root-Aufrufs
# kontrolliert, braucht diese Naehte nicht.
#
# Nicht verwaltet: baluhost-backend-local (#717) und die Tray-User-Unit.
# UNITS muss mit Modul 10, ci-deploy.sh und unit_drift.MANAGED_UNITS
# uebereinstimmen -- backend/tests/test_deploy_install_systemd_units.py prueft das.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEMPLATE_DIR="$INSTALL_DIR/deploy/install/templates"
VENV_BIN="$INSTALL_DIR/backend/.venv/bin"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
UNIT_BACKUP_DIR="${UNIT_BACKUP_DIR:-/var/backups/baluhost/units}"
BACKUP_KEEP=10

UNITS=(baluhost-backend baluhost-scheduler baluhost-webdav baluhost-monitoring)

# shellcheck source=../install/lib/common.sh
source "$INSTALL_DIR/deploy/install/lib/common.sh"

fail() {
    log_error "$*"
    exit 1
}

prune_backups() {
    local unit="$1" i excess
    local -a old
    shopt -s nullglob
    old=("$UNIT_BACKUP_DIR/$unit.service".*)
    shopt -u nullglob
    # Der Zeitstempel im Namen ist fest breit, die Glob-Sortierung ist also
    # chronologisch: vorne stehen die aeltesten.
    excess=$(( ${#old[@]} - BACKUP_KEEP ))
    for (( i = 0; i < excess; i++ )); do
        rm -f -- "${old[$i]}"
    done
}

if [[ "$EUID" -ne 0 && "${BALUHOST_UNITS_ALLOW_NONROOT:-}" != "1" ]]; then
    fail "must run as root (use sudo)."
fi

# ─── Dienstbenutzer ─────────────────────────────────────────────────
# Explizit > User= des laufenden Dienstes > Abbruch -- dasselbe Muster wie
# install-power-sudoers.sh, festgenagelt in test_deploy_service_user_resolution.
# BALUHOST_USER gilt nur fuer den manuellen Aufruf (siehe Test-Naehte oben).
SERVICE_USER="$(systemctl show -p User --value baluhost-backend.service 2>/dev/null || true)"
BALUHOST_USER="${BALUHOST_USER:-${SERVICE_USER:-}}"
if [[ -z "$BALUHOST_USER" ]]; then
    log_error "could not determine the service user from baluhost-backend.service (User=)"
    log_error "and BALUHOST_USER is unset. Set BALUHOST_USER explicitly."
    exit 1
fi
id -u "$BALUHOST_USER" >/dev/null 2>&1 \
    || fail "service user '$BALUHOST_USER' does not exist on this host."

# ─── 1. Rendern ─────────────────────────────────────────────────────
RENDER_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$RENDER_DIR"
    rm -f "$SYSTEMD_DIR"/.baluhost-*.service.new
}
trap cleanup EXIT

rendered=()
for unit in "${UNITS[@]}"; do
    out="$RENDER_DIR/$unit.service"
    process_template "$TEMPLATE_DIR/$unit.service" "$out" \
        "BALUHOST_USER=$BALUHOST_USER" \
        "INSTALL_DIR=$INSTALL_DIR" \
        "VENV_BIN=$VENV_BIN" \
        || fail "cannot render $unit.service"
    if leftover="$(grep -oE '@@[A-Z_]+@@' "$out" | sort -u | tr '\n' ' ')" && [[ -n "$leftover" ]]; then
        fail "$unit.service: unrendered placeholder(s) left: $leftover-- nothing installed."
    fi
    rendered+=("$out")
done

# ─── 2. Pruefen, alles oder nichts ──────────────────────────────────
if ! verify_out="$(systemd-analyze verify "${rendered[@]}" 2>&1)"; then
    echo "$verify_out" >&2
    fail "systemd-analyze verify rejected the rendered units -- nothing installed."
fi
# Nicht-fatale Hinweise von verify gehoeren trotzdem ins Deploy-Log.
if [[ -n "$verify_out" ]]; then
    echo "$verify_out" >&2
fi

# ─── 3. Vergleichen und ersetzen ────────────────────────────────────
install_args=(-m 0644)
if [[ "$EUID" -eq 0 ]]; then
    install_args+=(-o root -g root)
fi
stamp="$(date +%Y%m%d-%H%M%S-%N)"
changed=0

for unit in "${UNITS[@]}"; do
    src="$RENDER_DIR/$unit.service"
    dst="$SYSTEMD_DIR/$unit.service"
    if [[ -f "$dst" ]] && cmp -s "$src" "$dst"; then
        continue
    fi
    if [[ -f "$dst" ]]; then
        mkdir -p "$UNIT_BACKUP_DIR"
        cp -p "$dst" "$UNIT_BACKUP_DIR/$unit.service.$stamp"
        prune_backups "$unit"
    fi
    # Temp-Datei im Zielverzeichnis, damit mv ein atomarer Rename auf demselben
    # Dateisystem ist: systemd sieht nie eine halb geschriebene Unit. Der
    # Punkt-Praefix und die Endung .new halten sie aus systemds Unit-Suche.
    tmp="$SYSTEMD_DIR/.$unit.service.new"
    install "${install_args[@]}" "$src" "$tmp"
    mv -f "$tmp" "$dst"
    echo "CHANGED: $unit"
    changed=$(( changed + 1 ))
done

# ─── 4. Neu laden ───────────────────────────────────────────────────
# Auch ohne eigene Aenderung, wenn systemd eine Unit als veraltet meldet: nach
# einem gescheiterten daemon-reload stimmen die Dateien bereits, systemd faehrt
# aber die alte Fassung. Ein erneuter Aufruf -- den der Drift-Check als
# Reparatur empfiehlt -- muss genau diesen Fall beheben.
stale=0
for unit in "${UNITS[@]}"; do
    if [[ "$(systemctl show -p NeedDaemonReload --value "$unit.service" 2>/dev/null || true)" == "yes" ]]; then
        stale=1
    fi
done

if [[ "$changed" -eq 0 && "$stale" -eq 0 ]]; then
    echo "OK: all ${#UNITS[@]} units up to date"
    exit 0
fi

systemctl daemon-reload \
    || fail "systemctl daemon-reload failed -- unit files are written, systemd still runs the old ones."
if [[ "$changed" -eq 0 ]]; then
    echo "OK: all ${#UNITS[@]} units up to date, stale systemd state fixed by daemon-reload"
else
    echo "OK: $changed unit(s) replaced"
fi
```

- [ ] **Step 4: Tests laufen lassen, alle grün**

Run: `cd backend; python -m pytest tests/test_deploy_install_systemd_units.py -v --no-cov -p no:cacheprovider`
Expected: alle Tests PASS (unter Windows ggf. `test_ohne_root_und_ohne_testnaht_bricht_ab` ebenfalls PASS, da Git Bash nicht als root läuft).

Falls `date +%N` unter Git Bash keine Nanosekunden liefert und die Rotation deshalb Backups überschreibt (Test zählt < 10): Stempel auf `"$(date +%Y%m%d-%H%M%S)-$$-$RANDOM"` ändern ist **falsch** (bricht die chronologische Sortierung). Stattdessen prüfen mit `bash -c 'date +%N'`; GNU coreutils in Git for Windows unterstützt `%N`.

- [ ] **Step 5: Commit**

```bash
git add deploy/scripts/install-systemd-units.sh backend/tests/test_deploy_install_systemd_units.py
git commit -m "feat(deploy): install-systemd-units.sh gleicht Units mit Templates ab (#689)" -m "Rendert mit process_template wie Modul 10, prueft alle Units mit systemd-analyze verify bevor etwas geschrieben wird, ersetzt nur abweichende Dateien atomar mit Backup und laedt systemd nur bei Aenderung neu." -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: sudoers-Erlaubnis und Paritätstest der Unit-Listen

**Files:**
- Modify: `deploy/install/templates/baluhost-deploy-sudoers` (Block „Idempotent permission-grant scripts", nach den `install-power-sudoers.sh`-Zeilen)
- Test: `backend/tests/test_deploy_install_systemd_units.py` (anhängen)
- Test: `backend/tests/test_deploy_service_user_resolution.py` (Skript in die geprüften Listen aufnehmen)

**Interfaces:**
- Consumes: `UNITS=(…)` aus Task 1 (einzeilig); `SERVICES=(…)` in `deploy/install/modules/10-systemd-services.sh` und `deploy/scripts/ci-deploy.sh` (mehrzeilig); `app.services.unit_drift.MANAGED_UNITS`.
- Produces: sudoers-Zeilen, die Task 3 (`sudo -n bash "$INSTALL_DIR/deploy/scripts/install-systemd-units.sh"`) auf der Box erlauben.

- [ ] **Step 1: Tests anhängen**

In `backend/tests/test_deploy_install_systemd_units.py` den Import-Block um `import re` ergänzen (alphabetisch zwischen `import os` und `import shutil`; erst dieser Task benutzt ihn, in Task 1 meldete ruff sonst F401) und anhängen:

```python
# ─── Paritaet und sudoers ────────────────────────────────────────────

MODULE_10 = REPO / "deploy" / "install" / "modules" / "10-systemd-services.sh"
CI_DEPLOY = REPO / "deploy" / "scripts" / "ci-deploy.sh"
DEPLOY_SUDOERS = REPO / "deploy" / "install" / "templates" / "baluhost-deploy-sudoers"


def _bash_array(path: Path, name: str) -> set[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^{name}=\((.*?)\)", text, re.MULTILINE | re.DOTALL)
    assert match, f"{name}=( … ) nicht gefunden in {path.name}"
    return set(re.findall(r"baluhost-[a-z-]+", match.group(1)))


def test_alle_vier_unit_listen_sind_gleich():
    """Eine Unit, die nur in einer Liste steht, verfehlt still entweder den
    Installer, den Deploy-Abgleich, den Neustart oder den Drift-Check."""
    from app.services.unit_drift import MANAGED_UNITS

    expected = set(UNITS)
    assert _bash_array(SCRIPT, "UNITS") == expected
    assert _bash_array(MODULE_10, "SERVICES") == expected
    assert _bash_array(CI_DEPLOY, "SERVICES") == expected
    assert set(MANAGED_UNITS) == expected


def test_die_vorlage_erlaubt_genau_dieses_skript():
    zeilen = [
        z for z in DEPLOY_SUDOERS.read_text(encoding="utf-8").splitlines()
        if not z.lstrip().startswith("#") and "install-systemd-units.sh" in z
    ]
    assert len(zeilen) == 2, zeilen
    for z in zeilen:
        assert z.startswith("@@BALUHOST_USER@@ ALL=(root) NOPASSWD: ")
        assert "SETENV" not in z
        assert "*" not in z
        # Nichts hinter dem Skriptpfad: ohne Argumente kann der Deploy-User
        # dem Skript nichts unterschieben.
        assert z.endswith("@@INSTALL_DIR@@/deploy/scripts/install-systemd-units.sh")
    # Verankert gegen den Doppelpunkt, siehe test_ci_deploy_permission_sync:
    # "/bin/bash " steckt in "/usr/bin/bash ".
    pfade = {re.search(r"NOPASSWD:\s+(\S+)", z).group(1) for z in zeilen}
    assert pfade == {"/bin/bash", "/usr/bin/bash"}
```

In `backend/tests/test_deploy_service_user_resolution.py`:

- `PERMISSION_SCRIPTS` um `"install-systemd-units.sh",` ergänzen (nach `"install-power-sudoers.sh",`) und den Kommentar darüber von „Die vier Skripte" auf „Die fünf Skripte" ändern.
- `USER_RESOLVING_SCRIPTS` um `"install-systemd-units.sh",` ergänzen (nach `"install-deploy-sudoers.sh",`, vor dem Kommentar „Die beiden Vorbilder").
- In `test_die_skripte_finden_ihre_vorlagen_ueber_den_eigenen_ort` das Tupel um `"install-systemd-units.sh"` ergänzen.

- [ ] **Step 2: Tests laufen lassen**

Run: `cd backend; python -m pytest tests/test_deploy_install_systemd_units.py tests/test_deploy_service_user_resolution.py -v --no-cov -p no:cacheprovider`
Expected: `test_alle_vier_unit_listen_sind_gleich` PASS (die Listen stimmen heute schon überein), `test_die_vorlage_erlaubt_genau_dieses_skript` FAIL mit `assert 0 == 2`. `test_deploy_service_user_resolution.py` ist komplett PASS: Task 1 folgt dem festgenagelten Muster bereits, die Aufnahme sichert es nur gegen späteres Zerfallen.

- [ ] **Step 3: sudoers-Vorlage ergänzen**

In `deploy/install/templates/baluhost-deploy-sudoers` direkt nach der Zeile
`@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/bash @@INSTALL_DIR@@/deploy/scripts/install-power-sudoers.sh`
einfügen:

```
# systemd-Unit-Abgleich (#689) -- anders als die drei Skripte darueber bei
# JEDEM Deploy aufgerufen (Schritt 6b) und im Rollback. Das Skript schreibt
# Units mit frei waehlbarem User=/ExecStart= -- wer main kontrolliert, hat
# damit root; das galt ueber die drei install-*-Skripte schon vorher.
# Siehe .claude/rules/ci-cd-security.md, Known Gap 12.
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /bin/bash @@INSTALL_DIR@@/deploy/scripts/install-systemd-units.sh
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/bash @@INSTALL_DIR@@/deploy/scripts/install-systemd-units.sh
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend; python -m pytest tests/test_deploy_install_systemd_units.py tests/test_deploy_sudoers_units.py tests/test_ci_deploy_permission_sync.py -v --no-cov -p no:cacheprovider`
Expected: alle PASS (`test_deploy_sudoers_units.py` bleibt grün, weil die neuen Zeilen keine `systemctl restart`-Einträge sind).

- [ ] **Step 5: Commit**

```bash
git add deploy/install/templates/baluhost-deploy-sudoers backend/tests/test_deploy_install_systemd_units.py backend/tests/test_deploy_service_user_resolution.py
git commit -m "feat(deploy): sudoers erlaubt install-systemd-units.sh (#689)" -m "Zwei exakte NOPASSWD-Zeilen ohne Argumente; Paritaetstest haelt die vier Unit-Listen (Modul 10, ci-deploy, unit_drift, neues Skript) gleich." -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `ci-deploy.sh` — sudo-Kern auslagern, Schritt 6b, Rollback

**Files:**
- Modify: `deploy/scripts/ci-deploy.sh`
- Modify: `backend/tests/test_ci_deploy_permission_sync.py` (nur `_helper_source`)
- Create: `backend/tests/test_ci_deploy_unit_sync.py`

**Interfaces:**
- Consumes: Skript aus Task 1 unter `$INSTALL_DIR/deploy/scripts/install-systemd-units.sh`; sudoers aus Task 2.
- Produces (Bash-Funktionen in `ci-deploy.sh`, definiert **vor** `rollback()`, weil `--rollback` sofort nach dessen Definition läuft):
  - `sudo_repo_script <script>` → Return 0 = OK, 1 = Skript gescheitert (stderr des Skripts wurde ausgegeben), 2 = `sudo: a password is required` (stderr verschluckt). stdout des Skripts geht direkt durch.
  - `warn_deploy_sudoers_missing <label> <script>` → drei `log_warn`-Zeilen, die dritte enthält `sudo env BALUHOST_USER=$(id -un) bash $INSTALL_DIR/deploy/scripts/install-deploy-sudoers.sh`.
  - `run_permission_script <label> <script>` unverändert im Verhalten.

- [ ] **Step 1: Extraktor im bestehenden Test auf drei Funktionen umstellen**

In `backend/tests/test_ci_deploy_permission_sync.py` die Funktion `_helper_source` ersetzen durch:

```python
def _function_source(name: str) -> str:
    lines = _text().splitlines()
    start = next(i for i, z in enumerate(lines) if z.startswith(f"{name}() {{"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("}"))
    return "\n".join(lines[start:end + 1])


def _helper_source() -> str:
    # run_permission_script stuetzt sich seit #689 auf den ausgelagerten Kern
    # (sudo_repo_script) und die gemeinsame Anleitung; ohne sie liefe der
    # Helfer im Harness ins Leere.
    return "\n\n".join(_function_source(n) for n in (
        "sudo_repo_script", "warn_deploy_sudoers_missing", "run_permission_script"))
```

- [ ] **Step 2: Neue Testdatei schreiben**

`backend/tests/test_ci_deploy_unit_sync.py`:

```python
"""ci-deploy.sh gleicht die systemd-Units ab und stellt sie im Rollback wieder her (#689).

Die Reihenfolge im Hauptfluss und im Rollback ist nur textlich pruefbar: das
Skript braucht beim Laden sofort .env.production und PostgreSQL. Der
Status-Kontrakt des sudo-Kerns dagegen laeuft wirklich in bash, gegen ein
nachgebautes sudo -- dieselbe Technik wie test_ci_deploy_permission_sync.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

CI_DEPLOY = Path(__file__).resolve().parents[2] / "deploy" / "scripts" / "ci-deploy.sh"
UNITS_SCRIPT = "install-systemd-units.sh"
BASH = shutil.which("bash")


def _text() -> str:
    return CI_DEPLOY.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    lines = _text().splitlines()
    start = next(i for i, z in enumerate(lines) if z.startswith(f"{name}() {{"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("}"))
    return "\n".join(lines[start:end + 1])


def _step_6b() -> str:
    text = _text()
    return text[text.index("# ─── 6b."):text.index("# ─── 7.")]


def _case_branch(block: str, label: str) -> str:
    match = re.search(rf"^\s*{re.escape(label)}\)(.*?);;", block, re.MULTILINE | re.DOTALL)
    assert match, f"Zweig {label}) nicht gefunden"
    return match.group(1)


# ─── Hauptfluss ──────────────────────────────────────────────────────


def test_6b_liegt_nach_dem_frontend_build_und_vor_dem_neustart():
    text = _text()
    # Nicht nach dem Skriptpfad suchen: rollback() steht weiter oben in der
    # Datei und nennt denselben Pfad -- index() faende diesen Treffer.
    call = text.index('sudo_repo_script "$UNITS_SCRIPT"')
    assert text.index("npm run build") < call < text.index("# ─── 7. Service Restart")


def test_6b_rollt_bei_skriptfehler_zurueck_und_endet_rot():
    branch = _case_branch(_step_6b(), "*")
    assert "rollback" in branch
    assert "exit 1" in branch, "nach einem Rollback darf der Deploy nicht gruen enden"


def test_6b_warnt_nur_wenn_die_erlaubnis_fehlt():
    """Bis zur einmaligen Provisionierung darf jeder Deploy weiterlaufen --
    sonst waere jeder Deploy rot, bis jemand install-deploy-sudoers.sh ausfuehrt."""
    branch = _case_branch(_step_6b(), "2")
    assert "warn_deploy_sudoers_missing" in branch
    assert "rollback" not in branch
    assert "exit" not in branch


def test_6b_benutzt_den_gemeinsamen_sudo_kern():
    assert "sudo_repo_script" in _step_6b()
    assert "sudo -n bash" not in _step_6b()


# ─── Rollback ────────────────────────────────────────────────────────


def test_rollback_stellt_units_aus_dem_alten_baum_wieder_her():
    body = _function_source("rollback")
    reset = body.index('git reset --hard "$PREV_COMMIT"')
    units = body.index(UNITS_SCRIPT)
    restart = body.index("\n    restart_services")
    assert reset < units < restart


def test_rollback_bricht_am_unit_abgleich_nie_ab():
    body = _function_source("rollback")
    segment = body[body.index(UNITS_SCRIPT):body.index("\n    restart_services")]
    assert "exit" not in segment
    assert "return 1" not in segment
    assert "rollback" not in segment


def test_rollback_ueberspringt_einen_alten_commit_ohne_skript():
    body = _function_source("rollback")
    assert '[[ -f "$units_script" ]]' in body


def test_die_helfer_stehen_vor_rollback():
    """ci-deploy.sh --rollback ruft rollback() direkt nach dessen Definition
    auf. Stuende sudo_repo_script weiter unten, liefe der manuelle Rollback in
    'command not found'."""
    text = _text()
    manual = text.index('if [[ "${1:-}" == "--rollback" ]]; then')
    assert text.index("sudo_repo_script() {") < manual
    assert text.index("warn_deploy_sudoers_missing() {") < manual


# ─── Status-Kontrakt des sudo-Kerns, im Verhalten ────────────────────

_FAKE_SUDO = r'''
sudo() {
    echo "FAKE-SUDO args=[$*]"
    case "$FAKE_MODE" in
        password) echo "sudo: a password is required" >&2; return 1 ;;
        scriptfail) echo "boom from the script" >&2; return 3 ;;
        ok) echo "CHANGED: baluhost-webdav"; return 0 ;;
    esac
}
'''


def _status(tmp_path: Path, mode: str) -> subprocess.CompletedProcess:
    if BASH is None:
        pytest.skip("bash nicht verfuegbar")
    harness = "\n".join([
        "set -euo pipefail",
        _FAKE_SUDO,
        _function_source("sudo_repo_script"),
        'rc=0; sudo_repo_script /x/install-systemd-units.sh || rc=$?',
        'echo "STATUS=$rc"',
    ])
    return subprocess.run([BASH, "-c", harness], capture_output=True, text=True,
                          env={"FAKE_MODE": mode, "PATH": "/usr/bin:/bin"}, timeout=30)


@pytest.mark.parametrize("mode, status", [("ok", 0), ("scriptfail", 1), ("password", 2)])
def test_sudo_kern_liefert_den_status(tmp_path, mode, status):
    result = _status(tmp_path, mode)
    assert result.returncode == 0, result.stderr
    assert f"STATUS={status}" in result.stdout


def test_sudo_kern_reicht_stdout_und_skriptfehler_durch(tmp_path):
    ok = _status(tmp_path, "ok")
    assert "CHANGED: baluhost-webdav" in ok.stdout
    fail = _status(tmp_path, "scriptfail")
    assert "boom from the script" in fail.stderr
```

- [ ] **Step 3: Tests laufen lassen, die neuen müssen scheitern**

Run: `cd backend; python -m pytest tests/test_ci_deploy_unit_sync.py tests/test_ci_deploy_permission_sync.py -v --no-cov -p no:cacheprovider`
Expected: `test_ci_deploy_unit_sync.py` FAIL (kein `# ─── 6b.`, kein `sudo_repo_script() {`); die Verhaltenstests in `test_ci_deploy_permission_sync.py` ERROR/FAIL mit `StopIteration` im Extraktor (`sudo_repo_script` fehlt).

- [ ] **Step 4: Kopfkommentar anpassen**

In `deploy/scripts/ci-deploy.sh` Zeilen 4–6 ersetzen:

```bash
# Performs: pre-checks → DB backup → git pull → backend update →
#           alembic migration → frontend build → systemd unit sync →
#           service restart → health check.
```

- [ ] **Step 5: sudo-Kern und Anleitung nach `restart_services()` einfügen**

Direkt nach der schließenden `}` von `restart_services()` (vor `# ─── Companion (Tauri) Build + Install`) einfügen:

```bash
# ─── Repo-Skripte als root ────────────────────────────────────────────
#
# Fuehrt eines der version-kontrollierten Skripte unter deploy/scripts/ als root
# aus und unterscheidet, WARUM es scheitert (#570, #588, #689).
#
# Der Grund fuer die Unterscheidung: /etc/sudoers.d/baluhost-deploy ist die
# einzige sudoers-Datei, die dieser Deploy nicht neu rendern kann -- sie
# enthaelt genau die Erlaubnis, mit der die anderen installiert werden. Neue
# Zeilen der Vorlage erreichen eine bereits installierte Box deshalb nie, und
# der Aufruf scheiterte dann hinter einer nichtssagenden Zeile.
#
# Gemessen wird die WIRKUNG, nicht die Erlaubnis. Eine Vorabfrage per
# `sudo -n -l bash <script>` endet mit 0, sobald der Aufruf ueberhaupt erlaubt
# waere, auch MIT Passwort -- der Deploy-Benutzer ist in der sudo-Gruppe, also
# war jeder Aufruf "erlaubt" (#588, Deploy-Lauf 34236194380). Deshalb:
#   - `-n` fragt nie nach einem Passwort: fehlt die NOPASSWD-Regel, scheitert
#     der Aufruf sofort. Die Skripte sind idempotent, ein Fehlversuch schadet
#     nicht.
#   - `LC_ALL=C` haelt sudos eigene Meldung englisch (die Box spricht deutsch),
#     damit "a password is required" erkennbar ist.
#
# Rueckgabe: 0 = OK, 1 = das Skript selbst ist gescheitert (sein stderr steht
# im Log), 2 = die NOPASSWD-Regel fehlt. Was daraus folgt, entscheidet der
# Aufrufer: die Permission-Syncs warnen immer, der Unit-Abgleich rollt bei 1
# zurueck. Unter `set -e` nur als `sudo_repo_script … || status=$?` aufrufen.
sudo_repo_script() {
    local script="$1" err_file rc=0
    err_file="$(mktemp)"
    LC_ALL=C sudo -n bash "$script" 2>"$err_file" || rc=$?
    if [[ "$rc" -ne 0 ]] && grep -q '^sudo: a password is required' "$err_file"; then
        rm -f "$err_file"
        return 2
    fi
    cat "$err_file" >&2
    rm -f "$err_file"
    if [[ "$rc" -ne 0 ]]; then
        return 1
    fi
    return 0
}

# Die Anleitung fuer Status 2 -- an einer Stelle, damit Permission-Syncs und
# Unit-Abgleich denselben, geprueften Befehl ausgeben.
warn_deploy_sudoers_missing() {
    local label="$1" script="$2"
    log_warn "$label sync NOT PERMITTED: /etc/sudoers.d/baluhost-deploy on this box"
    log_warn "  predates the entry for $(basename "$script"). One-time fix:"
    # Der Benutzername wird HIER eingesetzt, nicht als $USER ausgegeben:
    # die Anweisung wird typischerweise in einer root-Shell ausgefuehrt, wo
    # $USER zu "root" wuerde. Die Datei wuerde dann fuer root gerendert, und
    # der Deploy-Benutzer verloere still alle NOPASSWD-Rechte -- der
    # naechste Deploy braeche beim Neustart der Dienste ab. `env` davor,
    # weil sudo Zuweisungen in der Kommandozeile ohne SETENV ablehnt.
    log_warn "    sudo env BALUHOST_USER=$(id -un) bash $INSTALL_DIR/deploy/scripts/install-deploy-sudoers.sh"
}
```

- [ ] **Step 6: `run_permission_script` auf den Kern umstellen**

Den gesamten Kommentarblock über `run_permission_script()` (beginnt mit `# Fuehrt eines der Permission-Skripte als root aus`) und die Funktion selbst ersetzen durch:

```bash
# Fuehrt eines der Permission-Skripte ueber sudo_repo_script aus. Jeder
# Fehlschlag bleibt eine Warnung: udev/polkit/sudoers-Syncs sind opt-in und
# duerfen einen Deploy nie abbrechen. Das `|| status=$?` ist Pflicht -- unter
# `set -e` braeche ein gescheiterter Sync sonst den ganzen Deploy ab.
run_permission_script() {
    local label="$1" script="$2" status=0
    if [[ ! -f "$script" ]]; then
        log_warn "$label script not found at $script (skipping)."
        return 0
    fi
    log_info "Re-applying $label..."
    sudo_repo_script "$script" || status=$?
    case "$status" in
        0) log_info "$label sync OK." ;;
        2) warn_deploy_sudoers_missing "$label" "$script"
           log_warn "  Until then $label stays at its installed state." ;;
        *) log_warn "$label sync failed (non-fatal - deploy continues)." ;;
    esac
}
```

- [ ] **Step 7: Rollback um den Re-Render ergänzen**

In `rollback()` direkt **vor** der Zeile `    restart_services` (nach dem Alembic-Downgrade-Block) einfügen:

```bash
    # Units aus dem zurueckgesetzten Baum, also mit den ALTEN Templates (#689).
    # Nur warnen: ein Rollback im Rollback gibt es nicht, und der Rollback soll
    # so weit kommen wie moeglich. Hat Schritt 6b an verify scheitern lassen,
    # ist nichts geschrieben worden und dies ein No-op.
    local units_script="$INSTALL_DIR/deploy/scripts/install-systemd-units.sh"
    if [[ -f "$units_script" ]]; then
        local units_status=0
        log_info "Restoring systemd units from $PREV_COMMIT templates..."
        sudo_repo_script "$units_script" || units_status=$?
        case "$units_status" in
            0) log_info "Systemd units match $PREV_COMMIT." ;;
            2) warn_deploy_sudoers_missing "Systemd units" "$units_script" ;;
            *) log_warn "Systemd unit restore failed - restarting with the units as installed." ;;
        esac
    else
        log_info "No install-systemd-units.sh at $PREV_COMMIT - units left as installed."
    fi
```

- [ ] **Step 8: Schritt 6b einfügen**

In `deploy/scripts/ci-deploy.sh` zwischen `log_info "Frontend build complete."` und `# ─── 7. Service Restart ─…` einfügen:

```bash
# ─── 6b. Systemd Units (#689) ────────────────────────────────────────
#
# Rendert die Unit-Templates und ersetzt abweichende Units, danach
# daemon-reload; der Neustart in Schritt 7 laesst sie greifen. Frueher
# schrieb nur Installer-Modul 10 Units, und eine Template-Aenderung blieb
# unter $INSTALL_DIR/deploy/ liegen -- --proxy-headers fehlte der laufenden
# Unit monatelang.
#   0: OK (die Ausgabe nennt ersetzte Units)
#   2: sudoers-Zeile fehlt auf dieser Box -> warnen, mit installierten Units
#      weiter (bis zur einmaligen Provisionierung der heutige Zustand)
#   sonst: Rollback. Rendert ein Template nicht oder lehnt verify ab, hat das
#      Skript nichts geschrieben; scheitert es beim Schreiben selbst, schreibt
#      der Rollback die alten Templates zurueck. Neuer Code mit alten Units
#      waere genau die stille Divergenz aus #689.

log_step "Systemd Units"

UNITS_SCRIPT="$INSTALL_DIR/deploy/scripts/install-systemd-units.sh"
units_status=0
sudo_repo_script "$UNITS_SCRIPT" || units_status=$?
case "$units_status" in
    0) log_info "Systemd units in sync with their templates." ;;
    2) warn_deploy_sudoers_missing "Systemd units" "$UNITS_SCRIPT"
       log_warn "  Until then the installed units stay as they are (the drift check reports differences)." ;;
    *) log_error "Systemd unit sync failed - rolling back."
       rollback
       exit 1 ;;
esac
```

- [ ] **Step 9: Kommentar zu Schritt 8c anpassen**

Den Kommentarblock unter `# ─── 8c. Systemd Unit Drift Smoke-Check (non-fatal, #689) ─…` ersetzen durch:

```bash
    # ─── 8c. Systemd Unit Drift Smoke-Check (non-fatal, #689) ────────────
    # Schritt 6b hat die Units bereits aus den Templates gerendert. Dieser
    # Check ist die unabhaengige zweite Messung danach: er vergleicht die
    # installierten Units und systemds effektives ExecStart mit den Templates
    # und WARNt bei jeder Differenz -- etwa einem Drop-in, das 6b nicht
    # anfasst, oder einer Box, auf der 6b mangels sudoers-Zeile nur warnen
    # konnte. Read-only, braucht kein sudo, endet immer mit 0.
```

- [ ] **Step 10: Tests laufen lassen**

Run: `cd backend; python -m pytest tests/test_ci_deploy_unit_sync.py tests/test_ci_deploy_permission_sync.py tests/test_deploy_install_systemd_units.py tests/test_deploy_service_user_resolution.py tests/services/test_unit_drift.py -v --no-cov -p no:cacheprovider`
Expected: alle PASS. Insbesondere: `test_jedes_permission_skript_laeuft_ueber_den_helfer` (genau ein `sudo -n bash "$script"`), `test_die_handlungsanweisung_kann_den_naechsten_deploy_nicht_lahmlegen`, die drei Verhaltenstests mit `DEPLOY-CONTINUES`, `test_ci_deploy_runs_the_check_after_the_health_check_non_fatally`.

- [ ] **Step 11: Syntax prüfen**

Run: `bash -n deploy/scripts/ci-deploy.sh; echo "exit=$?"` (aus dem Repo-Root; bei CRLF-Fehlern unter Windows: `tr -d '\r' < deploy/scripts/ci-deploy.sh | bash -n; echo "exit=$?"`)
Expected: `exit=0`

- [ ] **Step 12: Commit**

```bash
git add deploy/scripts/ci-deploy.sh backend/tests/test_ci_deploy_unit_sync.py backend/tests/test_ci_deploy_permission_sync.py
git commit -m "feat(deploy): ci-deploy gleicht systemd-Units ab und stellt sie im Rollback wieder her (#689)" -m "Neuer Schritt 6b vor dem Neustart; ein scheiternder Abgleich rollt zurueck, eine fehlende sudoers-Zeile warnt nur. Der sudo-Kern aus run_permission_script ist ausgelagert (Status 0/1/2), die Permission-Syncs bleiben rein warnend." -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Drift-Check-Reparaturzeile und Sicherheitsdoku

**Files:**
- Modify: `backend/app/services/unit_drift.py` (Docstring Z. 1–22, Reparaturzeile in `check_units`)
- Modify: `backend/app/services/CLAUDE.md:57` (Zeile `unit_drift.py`)
- Modify: `backend/tests/services/test_unit_drift.py:192-195`
- Modify: `.claude/rules/ci-cd-security.md` (Known Gaps nach Eintrag 11; Reviewer Checklist Zeile „Sudoers / systemd")

**Interfaces:**
- Consumes: Skriptpfad aus Task 1.
- Produces: keine neuen Schnittstellen.

- [ ] **Step 1: Test anpassen**

In `backend/tests/services/test_unit_drift.py` `test_fix_hint_names_installer_module` ersetzen durch:

```python
def test_fix_hint_names_the_unit_sync_script():
    """Die Reparatur ist der enge Abgleich aus #689, nicht der ganze
    Modul-10-Lauf (der zusaetzlich sudoers, polkit und udev schreibt)."""
    box = FakeBox()
    box.shows["baluhost-webdav"] = _show(reload="yes")
    hint = next(line for line in box.run() if "fix:" in line)
    assert f"sudo bash {INSTALL_DIR}/deploy/scripts/install-systemd-units.sh" in hint
    assert "--module 10-systemd-services" not in hint
```

- [ ] **Step 2: Test laufen lassen, er muss scheitern**

Run: `cd backend; python -m pytest tests/services/test_unit_drift.py -v --no-cov -p no:cacheprovider -k fix_hint`
Expected: FAIL (Hinweis nennt noch `install.sh --module 10-systemd-services`).

- [ ] **Step 3: `unit_drift.py` anpassen**

Die Reparaturzeile in `check_units` ersetzen:

```python
    if rerender:
        lines.append("WARN: fix: sudo bash "
                     f"{install_dir}/deploy/scripts/install-systemd-units.sh"
                     " — then restart the affected units")
```

Im Modul-Docstring den Absatz ab `Why this exists:` bis `…so it stayed green the whole time.` ersetzen durch:

```text
Why this exists: until #689 ``ci-deploy.sh`` never rendered unit files — only
``deploy/install/modules/10-systemd-services.sh`` did, on a manual installer
run. ``--proxy-headers`` sat in the template for months while the running
backend never had it, and the test for it read only the template text, so it
stayed green the whole time. Since #689 the deploy renders the units itself
(step 6b, ``deploy/scripts/install-systemd-units.sh``); this check stays as the
independent second measurement afterwards — it also catches drop-ins, which
the deploy never touches, and boxes where step 6b could only warn because the
sudoers entry was not provisioned yet.
```

In `backend/app/services/CLAUDE.md` die Zeile für `unit_drift.py` ersetzen durch:

```markdown
| `unit_drift.py` | Deploy smoke-check (`python -m app.services.unit_drift`, run by `ci-deploy.sh` after the health check, always exit 0): installed units + effective `ExecStart` from `systemctl show` vs. the rendered templates, plus drop-ins and `NeedDaemonReload`. Since #689 the deploy renders the units itself (step 6b, `deploy/scripts/install-systemd-units.sh`); this stays as the independent second measurement — it also catches drop-ins and boxes where 6b could only warn. `baluhost-backend-local` is excluded until #717 |
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend; python -m pytest tests/services/test_unit_drift.py -v --no-cov -p no:cacheprovider`
Expected: alle PASS.

- [ ] **Step 5: `ci-cd-security.md` ergänzen**

In `.claude/rules/ci-cd-security.md` die Checklist-Zeile ersetzen:

```markdown
- [ ] **Sudoers / systemd**: Changes under `deploy/install/templates/` to sudoers or service units? Verify the new rules are scoped to specific binaries with explicit args (no `ALL`, no globs that match user-controlled paths). **A change to one of the four managed unit templates (`baluhost-backend`, `-scheduler`, `-webdav`, `-monitoring`) takes effect as root on the next deploy** (step 6b, `deploy/scripts/install-systemd-units.sh`, #689) — review `User=`, `ExecStart=` and every path in it like code that runs as root.
```

Nach Known Gap 11 (endet mit `…instead of the box silently never rebooting.`) als neuen Absatz anfügen:

```markdown
12. **The deploy user may run `install-systemd-units.sh` as root, and it writes unit files** — Added in `deploy/install/templates/baluhost-deploy-sudoers` (#689) so a unit-template change reaches the box on the next deploy instead of sitting in `/opt/baluhost/deploy/` — `--proxy-headers` sat in the template for months while the running backend lacked it, leaving every LAN gate open. Two exact entries (`/bin/bash` and `/usr/bin/bash` + the pinned script path), no arguments, no wildcards, no `SETENV`. Unlike the three `install-*-sudoers.sh` grants, it runs on **every** deploy (step 6b) and again in `rollback()`, not only behind `SYNC_PERMISSIONS=1`. The script renders units with arbitrary `User=`/`ExecStart=` from repo templates and runs as root from a file inside `$INSTALL_DIR`. The real boundary is therefore **whoever can write under `$INSTALL_DIR` as the deploy user has root** — and the deploy user is the service user (`@@BALUHOST_USER@@`), owns `/opt/baluhost` (`deploy/update/run-update.sh` `chown -R`s it) and runs the backend without `NoNewPrivileges`. Two paths lead there: a commit on `main`, and code execution inside the backend process, which could rewrite this script (or, already today, `install-power-sudoers.sh`) and run it via `sudo -n bash`. Neither path is new — the three `install-*-sudoers.sh` grants have had the same shape since they were added; this entry names the boundary instead of leaving it implicit. Compensating controls against the `main` path: Layer 3 (`github.actor == 'Xveyn'`) and Layer 4 (`production` environment reviewer) gate every deploy. Against the backend-RCE path there is none specific to this entry; the tighter pattern is gap 10's spawn wrapper (root-owned, outside `/opt/baluhost`). Separately, as **integrity** checks rather than security controls: `systemd-analyze verify` rejects a malformed unit before anything is written, and a failed sync rolls the deploy back — a deliberately malicious unit passes both. The sudoers line reaches an already-installed box only via a one-time manual `install-deploy-sudoers.sh` run (same bootstrap quirk as the `baluhost-backend-local` restart line, `security-agent.md` Known Gap 10); until then step 6b warns with the exact command and the installed units stay as they are.
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/unit_drift.py backend/app/services/CLAUDE.md backend/tests/services/test_unit_drift.py .claude/rules/ci-cd-security.md
git commit -m "docs(deploy): Drift-Check und Sicherheitsregeln kennen den Unit-Abgleich (#689)" -m "Reparaturzeile zeigt auf install-systemd-units.sh statt auf Modul 10; ci-cd-security.md haelt die Grenze 'main == root' als Known Gap 12 fest und schaerft die Checklist fuer Unit-Templates." -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Abschlussprüfung

**Files:** keine Änderungen, außer ein Test deckt einen Fehler auf.

- [ ] **Step 1: Alle deploy-bezogenen Tests**

Run: `cd backend; python -m pytest tests/test_deploy_install_systemd_units.py tests/test_ci_deploy_unit_sync.py tests/test_ci_deploy_permission_sync.py tests/test_deploy_sudoers_units.py tests/test_deploy_service_user_resolution.py tests/test_deploy_proxy_headers.py tests/test_deploy_nginx_upstream.py tests/test_deploy_nginx_auth_limit.py tests/test_deploy_crypto_keys_provisioned.py tests/test_hardware_sudoers_scope.py tests/test_raid_sudoers_scope.py tests/services/test_unit_drift.py -v --no-cov -p no:cacheprovider`
Expected: alle PASS.

- [ ] **Step 2: Bash-Syntax aller angefassten Skripte**

Run (Repo-Root): `for f in deploy/scripts/ci-deploy.sh deploy/scripts/install-systemd-units.sh; do tr -d '\r' < "$f" | bash -n && echo "$f ok"; done`
Expected: beide `ok`.

- [ ] **Step 3: Ruff**

Run: `cd backend; python -m ruff check app/services/unit_drift.py tests/test_deploy_install_systemd_units.py tests/test_ci_deploy_unit_sync.py tests/test_ci_deploy_permission_sync.py tests/services/test_unit_drift.py`
Expected: `All checks passed!`

- [ ] **Step 4: Abnahme auf BaluNode vorbereiten (nach dem Merge, durch den Maintainer)**

Im PR-Text aufführen (Spec, Abschnitt „Abnahme auf BaluNode"):
1. Deploy ohne Provisionierung: Log zeigt in „Systemd Units" `NOT PERMITTED` + Reparaturbefehl, Deploy grün, Drift-Check PASS.
2. `sudo env BALUHOST_USER=sven bash /opt/baluhost/deploy/scripts/install-deploy-sudoers.sh`, dann Deploy per `workflow_dispatch`: `OK: all 4 units up to date`, Drift-Check PASS. Ein einmaliges `CHANGED:` beim ersten Lauf ist **kein** Fehlschlag: der Drift-Check ignoriert Leerzeichen am Zeilenende und Leerzeilen am Dateiende, `cmp` nicht. Maßgeblich ist, dass der nächste Lauf `up to date` meldet und die Dienste gesund sind.
3. `sudo bash /opt/baluhost/deploy/scripts/install-systemd-units.sh` → kein `CHANGED`; `systemctl show baluhost-backend -p NeedDaemonReload` → `no`.
