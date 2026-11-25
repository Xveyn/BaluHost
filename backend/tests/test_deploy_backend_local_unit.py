"""The local channel's units come from templates like every other unit (#717).

`baluhost-backend-local.service` / `.socket` were the only BaluHost units no
installer module wrote, and their templates were hard-wired: `User=baluhost`
(a user that does not exist on a box installed under another account) and an
`ExecStart` into `/opt/baluhost/venv`, where no venv lives. The production
box ran hand-written units instead, plus a drop-in that existed nowhere else.

Template text is checked here; that the units render and install is checked
with the real script in `test_deploy_install_systemd_units.py`, and against a
box's actual state in `tests/services/test_unit_drift.py`.
"""
import re
from pathlib import Path

import pytest

from app.services.unit_drift import parse_exec_start, render_template

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "deploy" / "install" / "templates"
MODULE_10 = REPO / "deploy" / "install" / "modules" / "10-systemd-services.sh"
SERVICE = TEMPLATES / "baluhost-backend-local.service"
SOCKET = TEMPLATES / "baluhost-backend-local.socket"

VALUES = {
    "BALUHOST_USER": "alice",
    "INSTALL_DIR": "/srv/balu host",
    "VENV_BIN": "/srv/balu host/backend/.venv/bin",
}


def _settings(text: str) -> list[str]:
    """Lines that set something: no comments, no blank lines."""
    return [l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]


def _rendered(path: Path) -> str:
    return render_template(path.read_text(encoding="utf-8"), VALUES)


@pytest.mark.parametrize("template", [SERVICE, SOCKET], ids=["service", "socket"])
def test_template_hard_wires_neither_a_user_nor_a_path(template):
    settings = "\n".join(_settings(template.read_text(encoding="utf-8")))

    assert "/opt/baluhost" not in settings
    assert not re.search(r"^(User|Group|SocketUser|SocketGroup)=(?!@@BALUHOST_USER@@$)",
                         settings, re.MULTILINE)


@pytest.mark.parametrize("template", [SERVICE, SOCKET], ids=["service", "socket"])
def test_template_renders_without_leftovers(template):
    assert "@@" not in _rendered(template)


def test_service_runs_as_the_service_user_from_the_install_dir():
    settings = _settings(_rendered(SERVICE))

    assert "User=alice" in settings
    assert "Group=alice" in settings
    assert "WorkingDirectory=/srv/balu host/backend" in settings
    assert "EnvironmentFile=/srv/balu host/.env.production" in settings


def test_service_starts_uvicorn_from_the_backend_venv_on_the_passed_socket():
    """The old template pointed at <install-dir>/venv; the venv is backend/.venv."""
    argv = parse_exec_start(SERVICE.read_text(encoding="utf-8"))

    assert argv[0] == "@@VENV_BIN@@/uvicorn"
    assert argv[1] == "app.main:app"
    assert argv[argv.index("--fd") + 1] == "3"
    # A TCP listener here would be a second, unauthenticated-by-channel way in.
    assert "--host" not in argv and "--port" not in argv


def test_service_declares_the_local_channel_and_never_the_primary_role():
    settings = _settings(SERVICE.read_text(encoding="utf-8"))

    assert 'Environment="BALUHOST_CHANNEL=local"' in settings
    # Was a drop-in on the production box only (#710); a fresh install lacked it.
    assert 'Environment="BALUHOST_PRIMARY_WORKER=0"' in settings


def test_service_is_bound_to_its_socket():
    settings = _settings(SERVICE.read_text(encoding="utf-8"))

    assert "Requires=baluhost-backend-local.socket" in settings


def test_socket_belongs_to_the_service_user_and_is_not_world_accessible():
    settings = _settings(_rendered(SOCKET))

    assert "ListenStream=/run/baluhost/local.sock" in settings
    assert "SocketUser=alice" in settings
    assert "SocketGroup=alice" in settings
    assert "SocketMode=0660" in settings


# ─── Installer ───────────────────────────────────────────────────────


def _function_body(name: str) -> str:
    text = MODULE_10.read_text(encoding="utf-8")
    match = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}", text, re.MULTILINE | re.DOTALL)
    assert match, f"{name}() not found in module 10"
    return match.group(1)


def test_module_10_installs_the_pair_as_an_optional_step():
    text = MODULE_10.read_text(encoding="utf-8")

    assert 'run_optional "Local channel units" install_local_channel_units' in text


def test_module_10_renders_with_the_same_three_values_as_the_core_units():
    body = _function_body("install_local_channel_units")

    for key in ("BALUHOST_USER", "INSTALL_DIR", "VENV_BIN"):
        assert f'"{key}=${key}"' in body


def test_module_10_enables_the_socket_and_never_the_service():
    """Enabled, the service would start at boot with no socket on fd 3."""
    text = MODULE_10.read_text(encoding="utf-8")
    body = _function_body("install_local_channel_units")

    assert 'LOCAL_CHANNEL_SOCKET="baluhost-backend-local.socket"' in text
    assert 'systemctl enable "$LOCAL_CHANNEL_SOCKET"' in body
    assert "baluhost-backend-local.service" not in body
    assert not re.search(r'"baluhost-backend-local"', text)
    # Not in the list whose members are all enabled as services.
    services = re.search(r"^SERVICES=\((.*?)\)", text, re.MULTILINE | re.DOTALL).group(1)
    assert "backend-local" not in services


def test_module_10_guards_every_command_of_the_optional_step():
    """run_optional switches errexit off inside the step (#683): an unguarded
    failure would be skipped silently."""
    body = _function_body("install_local_channel_units")
    commands = [l.strip() for l in body.splitlines()
                if re.match(r"\s*(chmod|systemctl) ", l)]

    assert commands, body
    for line in commands:
        assert line.endswith("|| return 1"), line
    assert re.search(r'"VENV_BIN=\$VENV_BIN" \|\| return 1', body)
