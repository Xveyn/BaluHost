"""Runner und Argumentbau: kein Wert ohne Enumeration, ein Aufruf, kein Hang."""
import subprocess
from unittest.mock import patch

import pytest

from app.plugins.installed.display_output import kscreen
from app.plugins.installed.display_output.models import DisplayMode, DisplayOutput


def _output(name: str, selected: bool, mode_ids: list[str]) -> DisplayOutput:
    return DisplayOutput(
        name=name,
        connected=True,
        selected=selected,
        modes=[
            DisplayMode(id=i, name=f"m{i}", width=1920, height=1080, refresh_rate=60.0)
            for i in mode_ids
        ],
    )


LIVE = [_output("HDMI-A-1", False, ["1", "9"]), _output("DP-3", True, ["57", "58"])]


class TestBuildApplyArgs:
    def test_one_call_carries_every_change(self):
        args = kscreen.build_apply_args(
            {"DP-3": (True, "57"), "HDMI-A-1": (False, None)}, LIVE
        )
        assert args == [
            "kscreen-doctor",
            "output.HDMI-A-1.disable",
            "output.DP-3.enable",
            "output.DP-3.mode.57",
        ]

    def test_order_follows_the_enumeration_not_the_request(self):
        # Deterministisch, damit der Vektor pruefbar ist - und unabhaengig
        # davon, in welcher Reihenfolge der Client seine Ausgaenge schickt.
        a = kscreen.build_apply_args({"DP-3": (True, None), "HDMI-A-1": (True, None)}, LIVE)
        b = kscreen.build_apply_args({"HDMI-A-1": (True, None), "DP-3": (True, None)}, LIVE)
        assert a == b
        assert a.index("output.HDMI-A-1.enable") < a.index("output.DP-3.enable")

    def test_an_output_the_request_omits_is_left_alone(self):
        args = kscreen.build_apply_args({"DP-3": (True, "58")}, LIVE)
        assert not any("HDMI-A-1" in a for a in args)

    def test_a_mode_on_a_deselected_output_is_ignored(self):
        # Siehe Spec 7: KWin behaelt die Modus-Wahl eines abgewaehlten
        # Ausgangs ohnehin; ein Fehler waere Schikane gegen eine UI, die
        # schlicht den angezeigten Zustand zurueckschickt.
        args = kscreen.build_apply_args({"HDMI-A-1": (False, "9")}, LIVE)
        assert args == ["kscreen-doctor", "output.HDMI-A-1.disable"]

    def test_mode_is_addressed_by_id_never_by_name(self):
        args = kscreen.build_apply_args({"DP-3": (True, "58")}, LIVE)
        assert "output.DP-3.mode.58" in args
        assert not any("@" in a for a in args)


class TestRunKscreen:
    # wayland_session_env() liest os.getuid(), das es unter Windows nicht
    # gibt - und wird als Argument ausgewertet, BEVOR das gepatchte
    # subprocess.run ueberhaupt aufgerufen wird. Ohne diesen Patch bricht
    # jeder Test hier schon beim Aufbau von env= ab, egal was subprocess.run
    # zurueckgeben soll. Gegenstand dieser Tests ist die Fehlerbehandlung
    # des Runners, nicht der Umgebungs-Helfer (eigene Tests in
    # tests/test_session_env.py) - deshalb wird er hier nur stillgelegt.
    @pytest.fixture(autouse=True)
    def _stub_session_env(self):
        with patch.object(kscreen, "wayland_session_env", return_value={}):
            yield

    def test_a_missing_binary_is_reported_not_raised(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            ok, message = kscreen.run_kscreen(["--dpms", "on"])
        assert ok is False
        assert "kscreen-doctor" in message

    def test_a_timeout_is_reported_not_raised(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("x", 10)):
            ok, message = kscreen.run_kscreen(["-j"])
        assert ok is False

    def test_a_nonzero_exit_is_a_failure(self):
        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        with patch("subprocess.run", return_value=completed):
            ok, message = kscreen.run_kscreen(["-j"])
        assert ok is False
        assert message == "boom"

    def test_the_call_always_carries_a_timeout(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        with patch("subprocess.run", return_value=completed) as run:
            kscreen.run_kscreen(["-j"])
        assert run.call_args.kwargs["timeout"] == kscreen.KSCREEN_TIMEOUT_SECONDS
        assert run.call_args.kwargs.get("shell") in (None, False)


class TestRunKscreenJson:
    def test_invalid_json_yields_none_instead_of_raising(self):
        with patch.object(kscreen, "run_kscreen", return_value=(True, "not json")):
            assert kscreen.run_kscreen_json() is None

    def test_a_failed_call_yields_none(self):
        with patch.object(kscreen, "run_kscreen", return_value=(False, "boom")):
            assert kscreen.run_kscreen_json() is None

    def test_valid_json_is_parsed(self):
        with patch.object(kscreen, "run_kscreen", return_value=(True, '{"outputs": []}')):
            assert kscreen.run_kscreen_json() == {"outputs": []}
