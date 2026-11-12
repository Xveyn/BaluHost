"""ci-deploy.sh endet rot, wenn der Health-Check scheitert (#753).

Nach einem gesunden Rollback gab ``rollback()`` 0 zurueck, und weil danach
nichts mehr kam, endete das ganze Skript mit 0. ``deploy-production.yml``
haengt Tag und Release an ``if: success()`` -- der Deploy war gruen und
taggte einen Commit, der nicht laeuft.

Der Schlussteil des Skripts laeuft hier wirklich in bash, mit nachgebauten
Funktionen: der Exit-Code ist der Kontrakt, an dem der Workflow haengt, und
der laesst sich am Text allein nicht ablesen (``set -e``, Rueckgabewerte).
"""
import shutil
import subprocess
from pathlib import Path

import pytest

CI_DEPLOY = Path(__file__).resolve().parents[2] / "deploy" / "scripts" / "ci-deploy.sh"
BASH = shutil.which("bash")

STEP_8 = "# ─── 8. Health Check"

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


def _text() -> str:
    return CI_DEPLOY.read_text(encoding="utf-8")


def _step_8() -> str:
    """Schritt 8 bis zum Dateiende -- das ist der Schluss des Hauptflusses."""
    text = _text()
    return text[text.index(STEP_8):]


def _run_step_8(tmp_path: Path, *, health: int, rollback_body: str) -> subprocess.CompletedProcess:
    """Fuehrt Schritt 8 mit denselben Shell-Optionen wie das Skript aus."""
    script = tmp_path / "step8.sh"
    script.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                "set -euo pipefail",
                f'INSTALL_DIR="{tmp_path}"',
                'VENV_BIN="$INSTALL_DIR/no-venv"',
                "DEPLOY_START=$(date +%s)",
                "NEW_COMMIT=new OLD_DB_REV=a NEW_DB_REV=b BACKUP_FILE=backup.sql",
                "INSTALL_COMPANION=0",
                'log_step()  { echo "STEP $*"; }',
                'log_info()  { echo "INFO $*"; }',
                'log_warn()  { echo "WARN $*"; }',
                'log_error() { echo "ERROR $*"; }',
                'save_deploy_state() { echo "CALL save_deploy_state"; }',
                'deploy_log_write()  { echo "CALL deploy_log_write $*"; }',
                'build_install_companion() { echo "CALL build_install_companion"; }',
                f"health_check() {{ return {health}; }}",
                f"rollback() {{ echo 'CALL rollback'; {rollback_body}; }}",
                _step_8(),
            ]
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        [BASH, str(script)], capture_output=True, text=True, timeout=60,
    )


def test_schritt_8_ist_der_schluss_des_skripts():
    """Die Tests unten pruefen den Exit-Code des Skripts ueber seinen
    Schlussteil. Das traegt nur, solange nach Schritt 8 kein weiterer
    Schritt folgt."""
    assert "\n# ─── 9." not in _step_8()
    assert _text().count(STEP_8) == 1


def test_gesunder_rollback_nach_health_fehler_endet_rot(tmp_path):
    result = _run_step_8(tmp_path, health=1, rollback_body="return 0")

    assert "CALL rollback" in result.stdout
    assert result.returncode == 1, (
        "nach einem Rollback darf der Deploy nicht gruen enden -- "
        "sonst taggt der Workflow einen Commit, der nicht laeuft"
    )
    assert "CALL save_deploy_state" not in result.stdout
    assert "CALL deploy_log_write success" not in result.stdout


def test_gescheiterter_rollback_endet_rot(tmp_path):
    """Gegenprobe: dieser Pfad war schon rot (rollback() ruft selbst exit 1)."""
    result = _run_step_8(tmp_path, health=1, rollback_body="exit 1")

    assert "CALL rollback" in result.stdout
    assert result.returncode == 1


def test_gesunder_deploy_endet_gruen(tmp_path):
    """Gegenprobe: der Erfolgspfad bleibt 0 -- auch wenn die beiden
    nicht-fatalen Smoke-Checks (hier ohne venv) nicht starten koennen."""
    result = _run_step_8(tmp_path, health=0, rollback_body="return 0")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CALL rollback" not in result.stdout
    assert "CALL save_deploy_state" in result.stdout
    assert "CALL deploy_log_write success" in result.stdout
