"""Deploy smoke-check: installed systemd units vs. their repo templates (#689).

The check reads the box's actual state (unit file on disk + `systemctl show`),
never just the template text — a template-only test stayed green for months
while the running backend lacked --proxy-headers.
"""
from pathlib import Path

import pytest

from app.services import unit_drift
from app.services.unit_drift import (
    MANAGED_UNITS,
    check_units,
    parse_exec_start,
    parse_show_argv,
    render_template,
)

_REPO_TEMPLATES = Path(__file__).resolve().parents[3] / "deploy" / "install" / "templates"

INSTALL_DIR = "/opt/baluhost"
USER = "sven"

TEMPLATE = """[Service]
User=@@BALUHOST_USER@@
WorkingDirectory=@@INSTALL_DIR@@/backend
ExecStart=@@VENV_BIN@@/uvicorn app.main:app \\
    --port 8000 \\
    --proxy-headers
"""

RENDERED = """[Service]
User=sven
WorkingDirectory=/opt/baluhost/backend
ExecStart=/opt/baluhost/backend/.venv/bin/uvicorn app.main:app \\
    --port 8000 \\
    --proxy-headers
"""

GOOD_ARGV = "/opt/baluhost/backend/.venv/bin/uvicorn app.main:app --port 8000 --proxy-headers"


def _show(argv=GOOD_ARGV, dropins="", reload="no", load="loaded", user=USER, name="x"):
    exec_start = (
        f"{{ path=/opt/baluhost/backend/.venv/bin/uvicorn ; argv[]={argv} ; "
        "ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
    )
    return {
        "LoadState": load,
        "FragmentPath": f"/etc/systemd/system/{name}.service",
        "DropInPaths": dropins,
        "NeedDaemonReload": reload,
        "User": user,
        "ExecStart": exec_start,
    }


class FakeBox:
    """Stands in for systemctl + the filesystem. Defaults to a box in sync."""

    def __init__(self):
        self.templates = {u: TEMPLATE for u in MANAGED_UNITS}
        self.installed = {u: RENDERED for u in MANAGED_UNITS}
        self.shows = {u: _show(name=u) for u in MANAGED_UNITS}

    def read_template(self, unit):
        return self.templates[unit]

    def read_file(self, path):
        unit = Path(path).stem
        if unit not in self.installed:
            raise FileNotFoundError(path)
        return self.installed[unit]

    def systemctl_show(self, unit):
        show = dict(self.shows[unit])
        if show["LoadState"] == "loaded":
            show["FragmentPath"] = f"/etc/systemd/system/{unit}.service"
        return show

    def run(self):
        return check_units(
            install_dir=INSTALL_DIR,
            read_template=self.read_template,
            read_file=self.read_file,
            systemctl_show=self.systemctl_show,
        )


def _warns(lines):
    return [line for line in lines if line.startswith("WARN")]


# ─── Parsing ─────────────────────────────────────────────────────────


def test_render_template_replaces_all_placeholders():
    out = render_template(TEMPLATE, {"BALUHOST_USER": USER, "INSTALL_DIR": INSTALL_DIR,
                                     "VENV_BIN": f"{INSTALL_DIR}/backend/.venv/bin"})
    assert out == RENDERED


def test_parse_exec_start_joins_continuation_lines():
    assert parse_exec_start(RENDERED) == GOOD_ARGV.split()


def test_parse_exec_start_ignores_exec_start_pre():
    text = "ExecStartPre=/usr/bin/rm -f /tmp/x\nExecStart=/bin/true --flag\n"
    assert parse_exec_start(text) == ["/bin/true", "--flag"]


def test_parse_show_argv_single_command():
    assert parse_show_argv(_show()["ExecStart"]) == [GOOD_ARGV.split()]


def test_parse_show_argv_multiple_commands():
    one = _show(argv="/bin/a -x")["ExecStart"]
    two = _show(argv="/bin/b -y")["ExecStart"]
    assert parse_show_argv(f"{one} ; {two}") == [["/bin/a", "-x"], ["/bin/b", "-y"]]


# ─── Checks ──────────────────────────────────────────────────────────


def test_box_in_sync_passes():
    lines = FakeBox().run()
    assert _warns(lines) == []
    assert any(line.startswith("PASS") for line in lines)


def test_installed_file_differs_from_template_warns_with_diff():
    box = FakeBox()
    box.installed["baluhost-backend"] = RENDERED.replace("    --proxy-headers\n", "")
    box.installed["baluhost-backend"] = box.installed["baluhost-backend"].replace(
        "--port 8000 \\", "--port 8000")
    box.shows["baluhost-backend"] = _show(
        argv="/opt/baluhost/backend/.venv/bin/uvicorn app.main:app --port 8000")
    warns = _warns(box.run())
    assert any("baluhost-backend" in w and "differs from template" in w for w in warns)
    assert any("--proxy-headers" in line for line in box.run())  # diff is shown


def test_dropin_overriding_exec_start_is_caught():
    """The #689 case: file on disk is fine, a drop-in changes what runs."""
    box = FakeBox()
    box.shows["baluhost-backend"] = _show(
        argv="/opt/baluhost/backend/.venv/bin/uvicorn app.main:app --port 8000",
        dropins="/etc/systemd/system/baluhost-backend.service.d/old.conf",
    )
    warns = _warns(box.run())
    assert any("effective ExecStart" in w for w in warns)
    assert any("drop-in" in w and "old.conf" in w for w in warns)


def test_redundant_dropin_is_still_reported():
    box = FakeBox()
    box.shows["baluhost-backend"] = _show(
        dropins="/etc/systemd/system/baluhost-backend.service.d/proxy-headers.conf")
    warns = _warns(box.run())
    assert len(warns) >= 1
    assert any("proxy-headers.conf" in w for w in warns)
    assert not any("effective ExecStart" in w for w in warns)


def test_need_daemon_reload_warns():
    box = FakeBox()
    box.shows["baluhost-webdav"] = _show(reload="yes")
    assert any("baluhost-webdav" in w and "daemon-reload" in w for w in _warns(box.run()))


def test_missing_unit_warns():
    box = FakeBox()
    box.shows["baluhost-monitoring"] = _show(load="not-found")
    del box.installed["baluhost-monitoring"]
    assert any("baluhost-monitoring" in w and "not installed" in w for w in _warns(box.run()))


def test_trailing_whitespace_and_final_newlines_are_not_drift():
    box = FakeBox()
    box.installed["baluhost-scheduler"] = RENDERED.replace("[Service]", "[Service]   ") + "\n\n"
    assert _warns(box.run()) == []


def test_unknown_service_user_warns_instead_of_guessing():
    box = FakeBox()
    box.shows["baluhost-backend"] = _show(user="")
    warns = _warns(box.run())
    assert any("service user" in w for w in warns)


def test_fix_hint_names_installer_module():
    box = FakeBox()
    box.shows["baluhost-webdav"] = _show(reload="yes")
    assert any("--module 10-systemd-services" in line for line in box.run())


def test_systemctl_failure_does_not_raise():
    box = FakeBox()

    def boom(unit):
        raise OSError("systemctl: not found")

    lines = check_units(install_dir=INSTALL_DIR, read_template=box.read_template,
                        read_file=box.read_file, systemctl_show=boom)
    assert _warns(lines)


def test_main_always_exits_zero(monkeypatch, capsys):
    def explode(**kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(unit_drift, "check_units", explode)
    assert unit_drift.main(["--install-dir", INSTALL_DIR]) == 0
    assert "WARN" in capsys.readouterr().out


# ─── Real templates ──────────────────────────────────────────────────


@pytest.mark.parametrize("unit", MANAGED_UNITS)
def test_real_templates_parse_to_a_command(unit):
    """Every managed template must yield an ExecStart the check can compare."""
    text = (_REPO_TEMPLATES / f"{unit}.service").read_text(encoding="utf-8")
    rendered = render_template(text, {"BALUHOST_USER": USER, "INSTALL_DIR": INSTALL_DIR,
                                      "VENV_BIN": f"{INSTALL_DIR}/backend/.venv/bin"})
    assert "@@" not in rendered, "unrendered placeholder left in template"
    argv = parse_exec_start(rendered)
    assert argv and argv[0].startswith(f"{INSTALL_DIR}/backend/.venv/bin/")


def test_real_backend_template_keeps_proxy_headers_in_effective_argv():
    text = (_REPO_TEMPLATES / "baluhost-backend.service").read_text(encoding="utf-8")
    argv = parse_exec_start(render_template(
        text, {"BALUHOST_USER": USER, "INSTALL_DIR": INSTALL_DIR,
               "VENV_BIN": f"{INSTALL_DIR}/backend/.venv/bin"}))
    assert "--proxy-headers" in argv
    assert "--forwarded-allow-ips=127.0.0.1" in argv


# ─── Deploy wiring ───────────────────────────────────────────────────

_CI_DEPLOY = Path(__file__).resolve().parents[3] / "deploy" / "scripts" / "ci-deploy.sh"


def test_ci_deploy_runs_the_check_after_the_health_check_non_fatally():
    text = _CI_DEPLOY.read_text(encoding="utf-8")
    call = "-m app.services.unit_drift --install-dir \"$INSTALL_DIR\""
    assert call in text, "ci-deploy.sh must run the unit drift smoke-check"
    # After a successful health check, not before: a WARN here must never
    # be able to trigger the rollback path.
    assert text.index("if health_check; then") < text.index(call) < text.index("rollback\nfi")
    line = next(l for l in text.splitlines() if call in l)
    following = text.splitlines()[text.splitlines().index(line) + 1]
    assert "|| log_warn" in following, "a failure to launch python must not fail the deploy"
