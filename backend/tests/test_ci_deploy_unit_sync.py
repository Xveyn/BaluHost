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
