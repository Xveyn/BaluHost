"""Der Companion-Build findet rustup-cargo auch ohne Login-Shell.

Gemessen auf BaluNode am 2026-09-21: `/opt/actions-runner/.path` -- die
PATH-Liste, die `runsvc.sh` per `export PATH=$(cat .path)` in jeden Job-Schritt
schiebt -- enthaelt `/home/sven/.cargo/bin` nicht. rustup haengt cargo
ausschliesslich ueber `~/.bashrc` / `~/.profile` an den PATH, und ein
GitHub-Actions-`run:`-Schritt liest beides nicht (nicht-interaktive
Non-Login-Shell).

Folge: `command -v cargo` in `build_install_companion()` scheitert auf einer
Box, auf der cargo 1.95 tatsaechlich installiert ist. Das Deploy meldet
"Rust/cargo not found ... Skipping", bleibt gruen -- und der Companion wird nie
installiert. Der Fehlschlag ist still: die Warnung geht in einem langen
Deploy-Log unter.

Geprueft wird im Verhalten, nicht im Text: die echte Funktion aus ci-deploy.sh
laeuft unter denselben Shell-Optionen wie im Deploy (`set -euo pipefail`),
gegen einen PATH ohne cargo und ein nachgebautes HOME mit rustup darin. Eine
reine Textpruefung koennte bestaetigen, dass irgendwo "cargo" steht, nicht dass
der Build tatsaechlich startet.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

CI_DEPLOY = Path(__file__).resolve().parents[2] / "deploy" / "scripts" / "ci-deploy.sh"

BASH = shutil.which("bash")

# Der PATH des Runners: kein ~/.cargo/bin, genau wie in .path auf BaluNode.
RUNNER_PATH = "/usr/bin:/bin"


def _text() -> str:
    return CI_DEPLOY.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    lines = _text().splitlines()
    start = next(i for i, z in enumerate(lines) if z.startswith(f"{name}() {{"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("}"))
    return "\n".join(lines[start:end + 1])


def test_das_deploy_skript_ist_ueberhaupt_lesbar():
    """Schutz gegen einen vakuum-gruenen Test: ohne Funktion waeren die
    Zusicherungen unten bedeutungslos."""
    assert CI_DEPLOY.is_file()
    assert "build_install_companion() {" in _text()


def _fake_cargo(bin_dir: Path, marke: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    cargo = bin_dir / "cargo"
    cargo.write_text(f"#!/bin/sh\necho {marke}\n", encoding="utf-8")
    cargo.chmod(0o755)
    return cargo


def _install_dir(tmp_path: Path) -> Path:
    """Ein /opt/baluhost-Doppel: client/ zum Hineinwechseln und ein fertiges
    .deb an der Stelle, an der der Tauri-Build es ablegen wuerde."""
    install_dir = tmp_path / "opt-baluhost"
    (install_dir / "client").mkdir(parents=True)
    deb_dir = install_dir / "client" / "src-tauri" / "target" / "release" / "bundle" / "deb"
    deb_dir.mkdir(parents=True)
    (deb_dir / "BaluHost Companion_0.1.0_amd64.deb").write_text("deb", encoding="utf-8")
    return install_dir


def _harness(install_dir: Path, *, mit_abschluss: bool = True) -> str:
    zeilen = [
        "set -euo pipefail",
        'log_step() { echo "[STEP] $*"; }',
        'log_info() { echo "[INFO] $*"; }',
        'log_warn() { echo "[WARN] $*"; }',
        # npm und sudo sind die beiden Aussenkontakte der Funktion. Das
        # protokollierte `command -v cargo` beweist, welches cargo der Build
        # tatsaechlich zu sehen bekommt.
        'npm() { echo "FAKE-NPM args=[$*] cargo=[$(command -v cargo)]"; }',
        'sudo() { echo "FAKE-SUDO args=[$*]"; }',
        f'INSTALL_DIR="{install_dir.as_posix()}"',
        _function_source("build_install_companion"),
        "build_install_companion",
    ]
    if mit_abschluss:
        # Beweist, dass kein Pfad der Funktion den Deploy abbricht.
        zeilen.append('echo "DEPLOY-CONTINUES"')
    return "\n".join(zeilen)


def _run(tmp_path: Path, *, env: dict, install_dir: Path) -> subprocess.CompletedProcess:
    if BASH is None:
        pytest.skip("bash nicht verfuegbar")
    return subprocess.run(
        [BASH, "-c", _harness(install_dir)],
        capture_output=True, text=True, env=env, timeout=60,
    )


def test_rustup_cargo_wird_ohne_login_shell_gefunden(tmp_path):
    """Der eigentliche Fehlerfall: cargo liegt in ~/.cargo/bin, steht aber
    nicht im PATH des Runners. Der Build muss trotzdem starten."""
    home = tmp_path / "home"
    _fake_cargo(home / ".cargo" / "bin", "rustup-cargo")
    install_dir = _install_dir(tmp_path)

    result = _run(tmp_path, install_dir=install_dir,
                  env={"PATH": RUNNER_PATH, "HOME": home.as_posix()})

    assert result.returncode == 0, result.stderr
    assert "Rust/cargo not found" not in result.stdout, "rustup war installiert"
    assert "FAKE-NPM" in result.stdout, "der Tauri-Build muss ueberhaupt starten"
    aufruf = next(z for z in result.stdout.splitlines() if z.startswith("FAKE-NPM"))
    assert "tauri:build" in aufruf
    assert (home / ".cargo" / "bin" / "cargo").as_posix() in aufruf
    assert "DEPLOY-CONTINUES" in result.stdout


def test_der_gefundene_build_wird_auch_gestaged_und_installiert(tmp_path):
    """Die Gegenprobe zum Test oben: cargo zu finden nuetzt nur, wenn die
    Funktion danach wirklich bis zum Installationsaufruf durchlaeuft."""
    home = tmp_path / "home"
    _fake_cargo(home / ".cargo" / "bin", "rustup-cargo")
    install_dir = _install_dir(tmp_path)

    result = _run(tmp_path, install_dir=install_dir,
                  env={"PATH": RUNNER_PATH, "HOME": home.as_posix()})

    assert result.returncode == 0, result.stderr
    assert (install_dir / ".companion" / "baluhost-companion.deb").is_file()
    assert "FAKE-SUDO" in result.stdout
    assert "install-companion.sh" in result.stdout
    assert "Companion installed/updated system-wide." in result.stdout


def test_cargo_home_schlaegt_das_heimatverzeichnis(tmp_path):
    """rustup laesst sich ueber CARGO_HOME umhaengen. Wer das getan hat, soll
    den Build nicht verlieren."""
    home = tmp_path / "home"
    home.mkdir()
    cargo_home = tmp_path / "anderswo"
    _fake_cargo(cargo_home / "bin", "umgehaengtes-cargo")
    install_dir = _install_dir(tmp_path)

    result = _run(tmp_path, install_dir=install_dir,
                  env={"PATH": RUNNER_PATH, "HOME": home.as_posix(),
                       "CARGO_HOME": cargo_home.as_posix()})

    assert result.returncode == 0, result.stderr
    aufruf = next(z for z in result.stdout.splitlines() if z.startswith("FAKE-NPM"))
    assert (cargo_home / "bin" / "cargo").as_posix() in aufruf


def test_ein_cargo_im_pfad_wird_nicht_verdraengt(tmp_path):
    """Boxen, auf denen cargo schon im PATH steht, aendern ihr Verhalten
    nicht: die Ergaenzung greift nur, wenn die Suche sonst leer ausgeht.
    Ein bedingungsloses Voranstellen von ~/.cargo/bin wuerde eine systemweite
    Rust-Installation stillschweigend ueberschatten."""
    home = tmp_path / "home"
    _fake_cargo(home / ".cargo" / "bin", "rustup-cargo")
    system_bin = tmp_path / "usr-local-bin"
    _fake_cargo(system_bin, "system-cargo")
    install_dir = _install_dir(tmp_path)

    result = _run(tmp_path, install_dir=install_dir,
                  env={"PATH": f"{system_bin.as_posix()}:{RUNNER_PATH}",
                       "HOME": home.as_posix()})

    assert result.returncode == 0, result.stderr
    aufruf = next(z for z in result.stdout.splitlines() if z.startswith("FAKE-NPM"))
    assert (system_bin / "cargo").as_posix() in aufruf
    assert ".cargo/bin/cargo" not in aufruf


def test_ohne_jedes_cargo_bleibt_es_bei_der_nicht_fatalen_warnung(tmp_path):
    """Die Ergaenzung darf den bisherigen Ausweg nicht kaputtmachen: ohne Rust
    wird uebersprungen, nicht abgebrochen -- der Backend-Deploy ist an dieser
    Stelle bereits erfolgreich."""
    home = tmp_path / "home"
    home.mkdir()
    install_dir = _install_dir(tmp_path)

    result = _run(tmp_path, install_dir=install_dir,
                  env={"PATH": RUNNER_PATH, "HOME": home.as_posix()})

    assert result.returncode == 0, result.stderr
    assert "Rust/cargo not found" in result.stdout
    assert "FAKE-NPM" not in result.stdout
    assert "DEPLOY-CONTINUES" in result.stdout


def test_die_warnung_nennt_den_grund_den_man_sonst_stundenlang_sucht(tmp_path):
    """Eine Box MIT rustup, aber unter einem anderen Konto, landet weiterhin
    hier. Dann muss die Meldung sagen, warum eine augenscheinlich vorhandene
    Rust-Installation nicht gesehen wird -- sonst sucht man am falschen Ende."""
    home = tmp_path / "home"
    home.mkdir()
    install_dir = _install_dir(tmp_path)

    result = _run(tmp_path, install_dir=install_dir,
                  env={"PATH": RUNNER_PATH, "HOME": home.as_posix()})

    warnungen = " ".join(z for z in result.stdout.splitlines() if z.startswith("[WARN]"))
    assert "CARGO_HOME" in warnungen
    assert "PATH" in warnungen
