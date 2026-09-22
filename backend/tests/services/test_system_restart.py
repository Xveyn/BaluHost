"""Tests für den systemctl-Helfer des Sammelneustarts."""
import subprocess

from app.services import system_restart


class _Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_backend_unit_is_last():
    """Der Backend-Neustart beendet den Prozess, der die Sequenz ausführt.

    Stünde er nicht am Ende, liefe alles danach nie."""
    assert system_restart.BALUHOST_UNITS[-1] == "baluhost-backend"
    assert system_restart.BACKEND_UNIT == "baluhost-backend"
    assert system_restart.SUPPORT_UNITS == system_restart.BALUHOST_UNITS[:-1]


def test_local_channel_unit_is_included():
    """Sie ist socket-aktiviert, läuft danach aber dauerhaft weiter.

    Ohne sie liefe der Companion-Kanal nach dem Neustart mit altem Code.
    """
    assert "baluhost-backend-local" in system_restart.SUPPORT_UNITS


def test_restart_unit_uses_argument_list_without_shell():
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return _Completed()

    result = system_restart.restart_unit("baluhost-webdav", runner=runner)

    assert result == system_restart.UnitResult("baluhost-webdav", True, None)
    args, kwargs = calls[0]
    assert args == ["sudo", "systemctl", "restart", "baluhost-webdav"]
    assert "shell" not in kwargs
    assert kwargs["timeout"] == 20.0


def test_restart_unit_reports_failure_with_stderr():
    def runner(args, **kwargs):
        return _Completed(returncode=1, stderr="Unit baluhost-webdav.service not found.\n")

    result = system_restart.restart_unit("baluhost-webdav", runner=runner)

    assert result.success is False
    assert "not found" in result.message


def test_restart_unit_falls_back_to_exit_code_when_output_is_empty():
    def runner(args, **kwargs):
        return _Completed(returncode=5)

    result = system_restart.restart_unit("baluhost-webdav", runner=runner)

    assert result.success is False
    assert "5" in result.message


def test_restart_unit_truncates_long_output():
    """Die Meldung landet in einer API-Antwort — sie bleibt kurz."""
    def runner(args, **kwargs):
        return _Completed(returncode=1, stderr="x" * 1000)

    result = system_restart.restart_unit("baluhost-webdav", runner=runner)

    assert len(result.message) <= 200


def test_restart_unit_handles_timeout():
    def runner(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=20.0)

    result = system_restart.restart_unit("baluhost-webdav", runner=runner)

    assert result.success is False
    assert "Zeit" in result.message


def test_restart_unit_handles_missing_binary():
    def runner(args, **kwargs):
        raise FileNotFoundError("sudo")

    result = system_restart.restart_unit("baluhost-webdav", runner=runner)

    assert result.success is False
    assert result.message


def test_restart_support_units_keeps_order_and_skips_backend():
    seen = []

    def runner(args, **kwargs):
        seen.append(args[-1])
        return _Completed()

    results = system_restart.restart_support_units(runner=runner)

    assert seen == [
        "baluhost-scheduler",
        "baluhost-monitoring",
        "baluhost-webdav",
        "baluhost-backend-local",
    ]
    assert [r.name for r in results] == seen
    assert all(r.success for r in results)


def test_restart_support_units_continues_after_a_failure():
    """Eine kaputte Unit darf die übrigen nicht verhindern."""
    def runner(args, **kwargs):
        if args[-1] == "baluhost-monitoring":
            return _Completed(returncode=1, stderr="boom")
        return _Completed()

    results = system_restart.restart_support_units(runner=runner)

    assert [(r.name, r.success) for r in results] == [
        ("baluhost-scheduler", True),
        ("baluhost-monitoring", False),
        ("baluhost-webdav", True),
        ("baluhost-backend-local", True),
    ]
