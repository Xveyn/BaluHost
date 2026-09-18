"""Der Deploy benennt den einen sudoers-Blindfleck, statt still zu scheitern (#570).

Gemessen im Deploy-Log vom 2026-09-07 (Lauf 34142444452):

    INFO  Re-applying power sudoers...
    sudo: Ein Passwort ist notwendig
    WARN  Power sudoers sync failed (non-fatal - deploy continues).

`/etc/sudoers.d/baluhost-deploy` ist die einzige der vier sudoers-Dateien, die
ci-deploy.sh nicht neu rendern kann -- sie enthaelt genau die Erlaubnis, mit
der die anderen drei installiert werden. Neue Zeilen der Vorlage erreichen eine
bereits installierte Box deshalb nie, und der Fehlschlag sah aus wie ein
beliebiger Fehler statt wie eine fehlende Provisionierung.

Geprueft wird zweifach: textlich (jede Ruecknahme der Diagnose faellt auf) und
seit #588 im Verhalten -- der Helfer laeuft wirklich in bash, gegen ein
nachgebautes sudo. Die rein textliche Fassung hatte bestaetigt, dass die alte
Vorabpruefung im Skript steht, nicht dass sie das Richtige misst.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

CI_DEPLOY = Path(__file__).resolve().parents[2] / "deploy" / "scripts" / "ci-deploy.sh"
DEPLOY_SUDOERS = (
    Path(__file__).resolve().parents[2]
    / "deploy" / "install" / "templates" / "baluhost-deploy-sudoers"
)


def _text() -> str:
    return CI_DEPLOY.read_text(encoding="utf-8")


def test_das_deploy_skript_ist_ueberhaupt_lesbar():
    """Schutz gegen einen vakuum-gruenen Test: ohne Inhalt waeren die
    Zusicherungen unten bedeutungslos."""
    assert CI_DEPLOY.is_file()
    assert "SYNC_PERMISSIONS" in _text()


def test_jedes_permission_skript_laeuft_ueber_den_helfer():
    """Kein direkter `sudo bash` mehr auf eines der drei Skripte.

    Der Helfer traegt die Diagnose; ein Aufruf daran vorbei haette sie
    nicht. Geprueft wird deshalb die Abwesenheit des alten Musters, nicht nur
    die Anwesenheit des neuen."""
    text = _text()
    assert "run_permission_script()" in text, "der Helfer muss definiert sein"
    # Zeilenfortsetzungen aufloesen, sonst stuenden Aufruf und Pfad in
    # verschiedenen Zeilen und die Zuordnung waere nicht pruefbar. Die alte
    # Fassung fragte nur, ob BEIDE Zeichenketten irgendwo in der Datei stehen --
    # das haette auch ein Aufruf am Helfer vorbei erfuellt.
    verbunden = re.sub(r"\\\s*\n\s*", " ", text)
    aufrufe = re.findall(r'run_permission_script\s+"[^"]+"\s+(\S+)', verbunden)
    for skript in ("install-amd-gpu-permissions.sh", "install-hardware-sudoers.sh",
                   "install-power-sudoers.sh"):
        assert any(skript in a for a in aufrufe), f"{skript} laeuft nicht ueber den Helfer"
    # Der Helfer ist die einzige Stelle, die eines dieser Skripte ausfuehrt --
    # und er tut es nie ohne -n (#588).
    assert text.count('sudo -n bash "$script"') == 1
    assert 'sudo bash "$script"' not in text
    assert 'sudo bash "$POWER_SUDOERS_SCRIPT"' not in text
    assert 'sudo bash "$HARDWARE_SUDOERS_SCRIPT"' not in text
    assert 'sudo bash "$AMD_GPU_SCRIPT"' not in text


def test_der_helfer_fragt_nicht_mehr_nach_der_erlaubnis():
    """`sudo -n -l <cmd>` endet mit 0, sobald der Aufruf ueberhaupt erlaubt
    waere -- auch MIT Passwort. Fuer ein Mitglied der sudo-Gruppe ist das jeder
    Befehl, die Vorabpruefung winkte also alles durch (#588, Deploy-Lauf
    34236194380). Gemessen wird jetzt die Wirkung, siehe die Verhaltenstests
    unten; die alte Pruefung darf nicht zurueckkommen. Kommentare duerfen sie
    nennen -- sie erklaeren, warum sie weg ist."""
    code = [z for z in _text().splitlines() if not z.lstrip().startswith("#")]
    assert not [z for z in code if "sudo -n -l" in z]


def test_die_meldung_nennt_den_befehl_der_es_behebt():
    """Eine Warnung ohne Handlungsanweisung kostet beim naechsten Mal wieder
    eine Stunde Suche."""
    text = _text()
    assert "install-deploy-sudoers.sh" in text
    assert "NOT PERMITTED" in text


def test_die_handlungsanweisung_kann_den_naechsten_deploy_nicht_lahmlegen():
    """Zwei Fallen, beide in der Review gefunden, beide hier festgenagelt.

    `$USER` in der ausgegebenen Zeile: die Anweisung wird in einer root-Shell
    ausgefuehrt, dort waere das "root". Die Datei wuerde fuer root gerendert,
    der Dienstbenutzer verloere alle NOPASSWD-Rechte, und der naechste Deploy
    braeche beim Neustart der Dienste ab.

    Fehlendes `env`: sudo lehnt Zuweisungen in der Kommandozeile ohne SETENV
    ab (env_reset ist Debian-Standard) -- der Befehl waere schlicht nicht
    ausfuehrbar.
    """
    zeile = next(
        z for z in _text().splitlines()
        if "install-deploy-sudoers.sh" in z and "log_warn" in z
    )
    assert "$USER" not in zeile, "Benutzername muss beim Drucken eingesetzt werden"
    assert "$(id -un)" in zeile
    assert "sudo env BALUHOST_USER=" in zeile


def test_die_vorlage_erlaubt_den_power_aufruf_ueberhaupt():
    """Die Gegenprobe zur Diagnose: waere der Eintrag in der Vorlage gar nicht
    vorhanden, waere nicht die Box veraltet, sondern das Repo falsch -- und die
    Handlungsanweisung ginge ins Leere."""
    zeilen = [
        z for z in DEPLOY_SUDOERS.read_text(encoding="utf-8").splitlines()
        if not z.lstrip().startswith("#")
    ]
    treffer = [z for z in zeilen if "install-power-sudoers.sh" in z]
    assert treffer, "die Vorlage muss den Aufruf erlauben"
    assert all("NOPASSWD" in z for z in treffer)
    # Beide bash-Pfade, weil sudo den aufgeloesten Pfad vergleicht. Verankert
    # gegen den Doppelpunkt: "/bin/bash " ist eine Teilzeichenkette von
    # "/usr/bin/bash ", eine blosse Suche waere also schon durch die zweite
    # Zeile erfuellt und koennte den Verlust der ersten nicht bemerken.
    pfade = {re.search(r"NOPASSWD:\s+(\S+)", z).group(1) for z in treffer}
    assert pfade == {"/bin/bash", "/usr/bin/bash"}


# ---------------------------------------------------------------------------
# Verhalten (#588): die echte Funktion aus ci-deploy.sh, mit nachgebautem sudo.
#
# Die Textpruefungen oben haben #577 nicht vor genau diesem Fehler bewahrt --
# sie bestaetigten, dass `sudo -n -l` im Skript steht, nicht dass es das
# Richtige misst. Deshalb laeuft der Helfer hier wirklich, unter denselben
# Shell-Optionen wie im Deploy (`set -euo pipefail`).
# ---------------------------------------------------------------------------

BASH = shutil.which("bash")

# sudo als Shell-Funktion ueberschattet das Programm. Nachgebildet ist das
# echte Verhalten fuer den Deploy-Benutzer auf BaluNode, der in der
# sudo-Gruppe ist:
#   - `sudo -n -l <cmd>` endet IMMER mit 0 (erlaubt -- notfalls mit Passwort).
#     Genau das hat die alte Vorabpruefung getaeuscht.
#   - fehlt die NOPASSWD-Regel (Modus "password"), scheitert jede Ausfuehrung:
#     mit -n sofort, ohne -n am fehlenden Terminal.
# Die erste Zeile protokolliert den Aufruf, damit -n und LC_ALL=C pruefbar sind.
_FAKE_SUDO = r'''
sudo() {
    if [[ "${1:-}" == "-n" && "${2:-}" == "-l" ]]; then
        echo "/usr/bin/bash ${*:3}"; return 0
    fi
    echo "FAKE-SUDO args=[$*] lc_all=[${LC_ALL:-}]"
    case "$FAKE_MODE" in
        password)
            if [[ "${1:-}" != "-n" ]]; then
                echo "sudo: a terminal is required to read the password" >&2
            fi
            echo "sudo: a password is required" >&2; return 1 ;;
        scriptfail) echo "boom from the script" >&2; return 3 ;;
        ok) echo "installed"; return 0 ;;
    esac
}
'''


def _helper_source() -> str:
    lines = _text().splitlines()
    start = next(i for i, z in enumerate(lines) if z.startswith("run_permission_script() {"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("}"))
    return "\n".join(lines[start:end + 1])


def _run_helper(tmp_path: Path, mode: str) -> subprocess.CompletedProcess:
    if BASH is None:
        pytest.skip("bash nicht verfuegbar")
    script = tmp_path / "install-power-sudoers.sh"
    script.write_text("#!/bin/bash\n", encoding="utf-8")
    harness = "\n".join([
        "set -euo pipefail",
        'log_info() { echo "[INFO] $*"; }',
        'log_warn() { echo "[WARN] $*"; }',
        "INSTALL_DIR=/opt/baluhost",
        _FAKE_SUDO,
        _helper_source(),
        f'run_permission_script "Power sudoers" "{script.as_posix()}"',
        # Beweist, dass ein gescheiterter Sync den Deploy nicht abbricht.
        'echo "DEPLOY-CONTINUES"',
    ])
    return subprocess.run(
        [BASH, "-c", harness], capture_output=True, text=True,
        env={"FAKE_MODE": mode, "PATH": "/usr/bin:/bin"}, timeout=30,
    )


def test_fehlendes_nopasswd_wird_als_not_permitted_mit_anleitung_gemeldet(tmp_path):
    """Genau der Fall aus Lauf 34236194380: die Regel fehlt, sudo -n verlangt
    ein Passwort. Frueher stand hier nur 'sync failed'."""
    result = _run_helper(tmp_path, "password")

    assert result.returncode == 0, result.stderr
    assert "NOT PERMITTED" in result.stdout
    assert "install-deploy-sudoers.sh" in result.stdout
    assert "sync failed" not in result.stdout
    assert "DEPLOY-CONTINUES" in result.stdout


def test_ein_scheiterndes_skript_bleibt_sync_failed(tmp_path):
    """Die Unterscheidung darf nicht jeden Fehlschlag zur Provisionierungsfrage
    machen: faellt das Skript selbst durch, ist die Anleitung falsch."""
    result = _run_helper(tmp_path, "scriptfail")

    assert result.returncode == 0, result.stderr
    assert "sync failed (non-fatal" in result.stdout
    assert "NOT PERMITTED" not in result.stdout
    assert "boom from the script" in result.stderr, "stderr des Skripts muss im Log landen"
    assert "DEPLOY-CONTINUES" in result.stdout


def test_erfolg_meldet_sync_ok(tmp_path):
    result = _run_helper(tmp_path, "ok")

    assert result.returncode == 0, result.stderr
    assert "Power sudoers sync OK." in result.stdout
    assert "installed" in result.stdout
    assert "DEPLOY-CONTINUES" in result.stdout


def test_sudo_wird_nie_ohne_n_und_mit_englischer_meldung_aufgerufen(tmp_path):
    """-n: nie ein Prompt, auch nicht im CI ohne Terminal. LC_ALL=C: die Box
    spricht deutsch ('Ein Passwort ist notwendig'), erkannt wird aber die
    englische Meldung."""
    result = _run_helper(tmp_path, "ok")

    aufruf = next(z for z in result.stdout.splitlines() if z.startswith("FAKE-SUDO"))
    assert "args=[-n bash " in aufruf
    assert "lc_all=[C]" in aufruf
