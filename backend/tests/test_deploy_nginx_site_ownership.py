"""Die nginx-Konfiguration gehoert root -- und der Deploy sagt es, wenn nicht (#862).

Der Dienstnutzer darf `systemctl reload nginx` (baluhost-deploy-sudoers), der
nginx-Master laeuft als root. Eine Site-Datei, die der Dienstnutzer schreiben
kann, macht aus Codeausfuehrung im Backend die Konfiguration eines
root-Prozesses. Auf BaluNode war sie `sven:sven 0664`.

Kein Skript im Repo hat diesen Zustand erzeugt: alle schreiben als root. Aber
keines hat ihn repariert -- `echo > datei`, `cp` und `sed -i` behalten Besitzer
und Modus einer vorhandenen Datei. Deshalb zwei Haelften:

  1. Die Skripte, die die Site schreiben, setzen Besitzer und Modus
     ausdruecklich. Das laeuft hier wirklich in bash; nur `chown` ist
     nachgebaut, weil die Suite nicht als root laeuft.
  2. Der Deploy misst den Ist-Zustand (`app.services.nginx_perms`) -- nur das
     erreicht eine Box, auf der der Installer laengst gelaufen ist. Die
     Einbindung ist textlich geprueft: ci-deploy.sh braucht beim Laden sofort
     .env.production und PostgreSQL.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
COMMON_SH = REPO / "deploy" / "install" / "lib" / "common.sh"
MODULE_11 = REPO / "deploy" / "install" / "modules" / "11-nginx.sh"
SELFSIGNED = REPO / "deploy" / "ssl" / "setup-selfsigned.sh"
CI_DEPLOY = REPO / "deploy" / "scripts" / "ci-deploy.sh"
VERIFY_INSTALL = REPO / "deploy" / "install" / "verify" / "verify-install.sh"
BASH = shutil.which("bash")

HELPER = "root_owned_0644"

_FAKE_CHOWN = r'''
chown() {
    echo "CHOWN $*"
    return "${FAKE_CHOWN_RC:-0}"
}
'''
_QUIET_LOGS = "log_info() { :; }; log_warn() { :; }; log_error() { :; }; log_step() { :; }; log_dry() { :; }"


def _function_source(path: Path, name: str) -> str:
    """Quelltext einer Funktion auf oberster Ebene; leer, wenn es sie nicht gibt."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, z in enumerate(lines) if z.startswith(f"{name}() {{")), None)
    if start is None:
        return ""
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("}"))
    return "\n".join(lines[start:end + 1])


def _bash(script: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    if BASH is None:
        pytest.skip("bash nicht verfuegbar")
    return subprocess.run(
        [BASH, "-c", script], capture_output=True, text=True, cwd=cwd, timeout=30,
        env={"PATH": "/usr/bin:/bin", **(env or {})},
    )


def _mode(path: Path) -> str:
    return oct(path.stat().st_mode & 0o777)


# ─── Der Helfer des Installers ───────────────────────────────────────


def _run_helper(tmp_path: Path, chown_rc: int = 0) -> tuple[subprocess.CompletedProcess, Path]:
    target = tmp_path / "baluhost"
    target.write_text("server {}\n", encoding="utf-8")
    target.chmod(0o664)
    script = "\n".join([
        f'source "{COMMON_SH}"',
        "set +e",
        _FAKE_CHOWN,
        f'{HELPER} "{target}"',
        'echo "RC=$?"',
    ])
    return _bash(script, tmp_path, {"FAKE_CHOWN_RC": str(chown_rc)}), target


def test_helfer_setzt_besitzer_root_und_modus_0644(tmp_path):
    result, target = _run_helper(tmp_path)
    assert "RC=0" in result.stdout, result.stderr
    assert f"CHOWN root:root {target}" in result.stdout
    assert _mode(target) == "0o644"


def test_helfer_meldet_ein_gescheitertes_chown(tmp_path):
    """Unter `set -e` bricht das Modul dann ab, statt eine Site zu aktivieren,
    die weiter dem Falschen gehoert."""
    result, _ = _run_helper(tmp_path, chown_rc=1)
    assert result.stdout.strip().endswith("RC=1"), result.stdout + result.stderr


# ─── Modul 11 ────────────────────────────────────────────────────────


def test_modul_11_setzt_die_rechte_nach_dem_rendern_und_vor_dem_test():
    text = MODULE_11.read_text(encoding="utf-8")
    render = text.index('process_template "$TEMPLATE" "$SITES_AVAILABLE"')
    harden = text.index(f'{HELPER} "$SITES_AVAILABLE"')
    assert render < harden < text.index("if nginx -t")


# ─── setup-selfsigned.sh ─────────────────────────────────────────────

_HTTPS_SITE = """server {
    listen 443 ssl http2;
    server_name alt;
    ssl_certificate /etc/letsencrypt/live/x/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/x/privkey.pem;
}
"""
_HTTP_SITE = "server {\n    listen 80;\n    server_name alt;\n}\n"


def _selfsigned_harness(*calls: str) -> str:
    return "\n".join([
        "set -euo pipefail",
        _QUIET_LOGS,
        _FAKE_CHOWN,
        _function_source(SELFSIGNED, HELPER),
        _function_source(SELFSIGNED, "install_ssl_snippets"),
        _function_source(SELFSIGNED, "update_nginx_config"),
        "DRY_RUN=false",
        *calls,
    ])


@pytest.mark.parametrize("site", [_HTTPS_SITE, _HTTP_SITE], ids=["https-vorhanden", "nur-http"])
def test_selfsigned_hinterlaesst_die_site_root_0644(tmp_path, site):
    """Beide Zweige: Zertifikatspfade per sed -i tauschen, oder die
    HTTPS-Vorlage per cp darueberlegen. Beides behaelt den Modus."""
    conf = tmp_path / "baluhost"
    conf.write_text(site, encoding="utf-8")
    conf.chmod(0o664)
    script = _selfsigned_harness(
        f'NGINX_CONF="{conf}"', "CERT_DIR=/etc/nginx/ssl",
        "HOSTNAME_NAME=box", "LAN_IP=192.0.2.10",
        "update_nginx_config",
    )
    # Das Skript sucht die Vorlage relativ zu sich selbst.
    result = _bash(script, SELFSIGNED.parent)
    assert result.returncode == 0, result.stderr
    assert f"CHOWN root:root {conf}" in result.stdout
    assert _mode(conf) == "0o644"
    assert "server_name box box.local 192.0.2.10;" in conf.read_text(encoding="utf-8")


def test_selfsigned_hinterlaesst_die_snippets_root_0644(tmp_path):
    snippets = tmp_path / "snippets"
    snippets.mkdir()
    for name in ("ssl-params.conf", "security-headers.conf"):
        (snippets / name).write_text("# alt\n", encoding="utf-8")
        (snippets / name).chmod(0o666)
    script = _selfsigned_harness(f'SNIPPETS_DIR="{snippets}"', "install_ssl_snippets")
    result = _bash(script, SELFSIGNED.parent)
    assert result.returncode == 0, result.stderr
    for name in ("ssl-params.conf", "security-headers.conf"):
        assert f"CHOWN root:root {snippets / name}" in result.stdout
        assert _mode(snippets / name) == "0o644"
        assert (snippets / name).read_text(encoding="utf-8") != "# alt\n"


# ─── Der Deploy misst den Ist-Zustand ────────────────────────────────


def _success_branch() -> str:
    text = CI_DEPLOY.read_text(encoding="utf-8")
    # rollback() weiter oben enthaelt dasselbe `if health_check; then` --
    # gemeint ist der Hauptfluss.
    start = text.index("if health_check; then", text.index("# ─── 8. Health Check"))
    return text[start:text.index("\nelse\n", start)]


def test_deploy_ruft_den_check_nach_bestandenem_health_check():
    assert "-m app.services.nginx_perms" in _success_branch()


def test_deploy_scheitert_nie_an_dem_check():
    """Wie 8b und 8c: ein Befund ist eine Zeile im Log, kein roter Deploy --
    die Box laeuft, und beheben kann es nur ein Mensch mit sudo."""
    line = next(z for z in _success_branch().splitlines() if "app.services.nginx_perms" in z)
    following = _success_branch().split(line, 1)[1].lstrip().splitlines()[0]
    assert "--strict" not in line
    assert following.startswith("|| log_warn")


def test_verify_install_prueft_streng():
    """Nach einer Neuinstallation gibt es keinen Grund fuer eine Ausnahme."""
    text = VERIFY_INSTALL.read_text(encoding="utf-8")
    line = next((z for z in text.splitlines() if "app.services.nginx_perms" in z), "")
    assert "--strict" in line
