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
    OPTIONAL_UNIT_FILES,
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

SOCKET_TEMPLATE = """[Socket]
ListenStream=/run/baluhost/local.sock
SocketUser=@@BALUHOST_USER@@
"""

SOCKET_RENDERED = """[Socket]
ListenStream=/run/baluhost/local.sock
SocketUser=sven
"""


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
        name = Path(path).name
        unit = name if name in self.installed else Path(path).stem
        if unit not in self.installed:
            raise FileNotFoundError(path)
        return self.installed[unit]

    def systemctl_show(self, unit):
        if unit not in self.shows:
            # What systemctl answers for a unit that is not installed.
            return {"LoadState": "not-found", "FragmentPath": "", "DropInPaths": "",
                    "NeedDaemonReload": "no", "User": "", "ExecStart": ""}
        show = dict(self.shows[unit])
        if show["LoadState"] == "loaded":
            show["FragmentPath"] = f"/etc/systemd/system/{unit_drift.unit_file_name(unit)}"
        return show

    def install_local_channel(self):
        """Put the optional pair on the box, in sync with its templates."""
        service, socket = OPTIONAL_UNIT_FILES
        self.templates[service] = TEMPLATE
        self.installed[service] = RENDERED
        self.shows[service] = _show(name=service)
        self.templates[socket] = SOCKET_TEMPLATE
        self.installed[socket] = SOCKET_RENDERED
        self.shows[socket] = {**_show(name=socket), "ExecStart": ""}

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


def test_fix_hint_names_the_unit_sync_script():
    """Die Reparatur ist der enge Abgleich aus #689, nicht der ganze
    Modul-10-Lauf (der zusaetzlich sudoers, polkit und udev schreibt)."""
    box = FakeBox()
    box.shows["baluhost-webdav"] = _show(reload="yes")
    hint = next(line for line in box.run() if "fix:" in line)
    assert f"sudo bash {INSTALL_DIR}/deploy/scripts/install-systemd-units.sh" in hint
    assert "--module 10-systemd-services" not in hint


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
    # The anchor is the rollback call of the health check's else branch — the
    # last one in the file. (It used to be "rollback\nfi"; since #753 an
    # `exit 1` follows the rollback.)
    assert text.index("if health_check; then") < text.index(call) < text.rindex("\n    rollback\n")
    line = next(l for l in text.splitlines() if call in l)
    following = text.splitlines()[text.splitlines().index(line) + 1]
    assert "|| log_warn" in following, "a failure to launch python must not fail the deploy"


# ─── The local channel: optional, a service plus its socket (#717) ───


def test_box_without_the_local_channel_passes_with_four_units():
    assert FakeBox().run() == ["PASS: 4 systemd units match their templates"]


def test_local_channel_in_sync_passes_with_six_units():
    box = FakeBox()
    box.install_local_channel()

    assert box.run() == ["PASS: 6 systemd units match their templates"]


def test_local_service_differing_from_its_template_warns():
    """The state of the production box before #717: a hand-written unit that
    no template described."""
    box = FakeBox()
    box.install_local_channel()
    service = OPTIONAL_UNIT_FILES[0]
    box.installed[service] = RENDERED.replace("User=sven", "User=baluhost")

    lines = box.run()

    assert any(f"{service}: /etc/systemd/system/{service} differs from template" in l
               for l in lines)
    assert any("install-systemd-units.sh" in l for l in lines)


def test_local_socket_differing_from_its_template_warns():
    box = FakeBox()
    box.install_local_channel()
    socket = OPTIONAL_UNIT_FILES[1]
    box.installed[socket] = SOCKET_RENDERED.replace("SocketUser=sven", "SocketUser=baluhost")

    lines = box.run()

    assert any(f"{socket}: /etc/systemd/system/{socket} differs from template" in l
               for l in lines)


def test_socket_unit_is_not_asked_for_an_exec_start():
    """A socket runs no command; its empty ExecStart is not drift."""
    box = FakeBox()
    box.install_local_channel()

    assert not any("ExecStart" in l for l in box.run())


def test_dropin_on_the_local_service_is_reported():
    """primary-worker.conf from #710 lived on the box only."""
    box = FakeBox()
    box.install_local_channel()
    service = OPTIONAL_UNIT_FILES[0]
    box.shows[service] = _show(
        name=service,
        dropins="/etc/systemd/system/baluhost-backend-local.service.d/primary-worker.conf",
    )

    lines = _warns(box.run())

    assert len(lines) == 1
    assert "primary-worker.conf" in lines[0]


def test_half_installed_local_channel_is_reported():
    box = FakeBox()
    box.install_local_channel()
    service, socket = OPTIONAL_UNIT_FILES
    del box.shows[service]

    lines = box.run()

    assert any(f"{service}: not installed" in l for l in lines)
    assert not any(f"{socket}:" in l for l in lines)


def test_failing_query_for_the_local_channel_does_not_hide_the_core_units():
    box = FakeBox()
    real_show = box.systemctl_show

    def _show_or_fail(unit):
        if unit in OPTIONAL_UNIT_FILES:
            raise RuntimeError("systemctl timed out")
        return real_show(unit)

    box.systemctl_show = _show_or_fail

    lines = box.run()

    assert lines == ["WARN: local channel units: check failed: systemctl timed out"]


@pytest.mark.parametrize("name", OPTIONAL_UNIT_FILES)
def test_real_local_channel_templates_render_completely(name):
    text = (_REPO_TEMPLATES / name).read_text(encoding="utf-8")
    rendered = render_template(text, {
        "BALUHOST_USER": USER, "INSTALL_DIR": INSTALL_DIR,
        "VENV_BIN": f"{INSTALL_DIR}/backend/.venv/bin",
    })

    assert "@@" not in rendered


def test_unit_file_name_keeps_a_suffix_and_adds_the_default():
    assert unit_drift.unit_file_name("baluhost-backend") == "baluhost-backend.service"
    assert unit_drift.unit_file_name("baluhost-backend-local.socket") == "baluhost-backend-local.socket"
    assert unit_drift.unit_file_name("baluhost-backend-local.service") == "baluhost-backend-local.service"


def test_local_service_with_another_effective_command_is_caught():
    """The file can match its template while a drop-in swaps the command."""
    box = FakeBox()
    box.install_local_channel()
    service = OPTIONAL_UNIT_FILES[0]
    box.shows[service] = _show(
        name=service,
        argv="/opt/baluhost/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9000",
    )

    lines = box.run()

    assert any(f"{service}: effective ExecStart differs from template" in l for l in lines)
