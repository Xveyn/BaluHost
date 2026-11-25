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
    assert "if ! has_trixie_backports" in text and "trixie-backports.list" in text


def _bash(snippet: str, env: dict | None = None) -> subprocess.CompletedProcess:
    import os

    return subprocess.run(
        ["bash", "-c", f'source "{_SCRIPT}"; {snippet}'],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, **(env or {})},
    )


def _has_backports(tmp_path, name: str, content: str) -> bool:
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return _bash(f'has_trixie_backports "{f}" "{tmp_path}/fehlt.list"').returncode == 0


def test_sourcing_installs_nothing():
    # Ohne root und ohne main-Aufruf: kein Fehler, keine Ausgabe
    result = _bash("true")
    assert result.returncode == 0 and result.stdout == ""


def test_backports_detection_ignores_comments(tmp_path):
    assert not _has_backports(tmp_path, "a.list", "# deb http://deb.debian.org/debian trixie-backports main\n")
    assert _has_backports(tmp_path, "b.list", "deb http://deb.debian.org/debian trixie-backports main\n")
    assert _has_backports(tmp_path, "c.sources", "Types: deb\nSuites: trixie-backports\nComponents: main\n")
    assert not _has_backports(tmp_path, "d.list", "deb http://deb.debian.org/debian trixie main\n")


def test_backports_detection_ignores_disabled_deb822(tmp_path):
    assert not _has_backports(
        tmp_path, "a.sources",
        "Types: deb\nURIs: http://deb.debian.org/debian\nSuites: trixie-backports\nEnabled: no\n",
    )
    # Die deaktivierte Stanza steckt eine aktive nicht an (und umgekehrt)
    assert _has_backports(
        tmp_path, "b.sources",
        "Suites: trixie-backports\nEnabled: no\n\nTypes: deb\nSuites: trixie trixie-backports\n",
    )
    assert not _has_backports(
        tmp_path, "c.sources",
        "Suites: trixie-backports\nEnabled: No\n\nSuites: trixie\n",
    )


def test_codename_must_be_trixie(tmp_path):
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=debian\nVERSION_CODENAME=trixie\n', encoding="utf-8")
    assert _bash("check_codename", {"OS_RELEASE_FILE": str(os_release)}).returncode == 0
    os_release.write_text('ID=debian\nVERSION_CODENAME=bookworm\n', encoding="utf-8")
    result = _bash("check_codename", {"OS_RELEASE_FILE": str(os_release)})
    assert result.returncode != 0
    assert "trixie" in result.stderr and "bookworm" in result.stderr
    missing = _bash("check_codename", {"OS_RELEASE_FILE": str(tmp_path / "fehlt")})
    assert missing.returncode != 0


def test_lego_is_an_optional_feature_off_by_default():
    assert "LEGO)" in _FEATURES.read_text(encoding="utf-8")
    assert "install-lego.sh" in _FEATURES.read_text(encoding="utf-8")
    config = _CONFIG.read_text(encoding="utf-8")
    assert ': "${ENABLE_LEGO:=false}"' in config
    assert "ENABLE_LEGO" in config.split("config_vars=(")[1]
