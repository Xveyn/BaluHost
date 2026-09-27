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
import re
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
