"""Installer-Schritt fuer lego (Plugin local_tls): Backports-Befehl, Syntax, Katalog."""
import subprocess
from pathlib import Path

_DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
_SCRIPT = _DEPLOY / "scripts" / "install-lego.sh"
_FEATURES = _DEPLOY / "install" / "lib" / "features.sh"
_CONFIG = _DEPLOY / "install" / "lib" / "config.sh"


def test_script_installs_from_trixie_backports():
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "-t trixie-backports lego" in text


def test_scripts_are_valid_bash():
    for path in (_SCRIPT, _FEATURES, _CONFIG):
        result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, f"{path.name}: {result.stderr}"


def test_backports_source_only_added_when_missing():
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "if ! grep" in text and "trixie-backports.list" in text


def test_lego_is_an_optional_feature_off_by_default():
    assert "LEGO)" in _FEATURES.read_text(encoding="utf-8")
    assert "install-lego.sh" in _FEATURES.read_text(encoding="utf-8")
    config = _CONFIG.read_text(encoding="utf-8")
    assert ': "${ENABLE_LEGO:=false}"' in config
    assert "ENABLE_LEGO" in config.split("config_vars=(")[1]
