"""Das Modul, das ``org.kde.ScreenBrightness`` kennt: Parser, Rechnen, Runner.

Kein Test spricht mit einem echten Bus. Die Fixture
``fixtures/screenbrightness_balunode.txt`` ist eine **gemessene** Ausgabe von

    qdbus6 org.kde.ScreenBrightness /org/kde/ScreenBrightness/display13 \
        org.freedesktop.DBus.Properties.GetAll org.kde.ScreenBrightness.Display

auf BaluNode (2026-09-22) — nachmessen statt von Hand bearbeiten. **Eine
Ausnahme:** ``Label`` traegt einen neutralen Namen statt des gemessenen
EDID-Namens; das Repo ist oeffentlich, und welches Modell dort haengt, ist fuer
keinen Test von Belang. Reihenfolge, Schluesselnamen, Zahlen und die Schreibweise
von ``false`` sind unveraendert — daran haengen die Tests.
"""
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.plugins.installed.display_output import brightness

MEASURED = (Path(__file__).parent / "fixtures" / "screenbrightness_balunode.txt").read_text(
    encoding="utf-8"
)

# Gemessen am selben Tag: die Objektliste traegt genau einen Eintrag, obwohl
# zwei Ausgaenge verbunden sind — DP-3 war abgeschaltet.
MEASURED_IDS = "display13\n"


class TestParseDisplayIds:
    def test_the_measured_list_yields_its_single_id(self):
        assert brightness.parse_display_ids(MEASURED_IDS) == ["display13"]

    def test_several_ids_keep_their_order(self):
        assert brightness.parse_display_ids("display13\ndisplay7\n") == ["display13", "display7"]

    def test_no_displays_is_an_empty_list_not_an_error(self):
        assert brightness.parse_display_ids("") == []
        assert brightness.parse_display_ids("\n  \n") == []

    def test_an_id_that_could_escape_the_object_path_is_dropped(self):
        # Die IDs baut powerdevil, nicht der Client — aber sie werden zu einem
        # Objektpfad zusammengesetzt. Was kein reiner Pfadbestandteil ist,
        # wird hier verworfen, nicht escaped.
        assert brightness.parse_display_ids("display13\n../../evil\nfoo bar\n") == ["display13"]


class TestObjectPath:
    def test_an_enumerated_id_becomes_its_object_path(self):
        assert brightness.object_path("display13") == "/org/kde/ScreenBrightness/display13"

    @pytest.mark.parametrize("bad", ["", "a/b", "../x", "with space", "dot.dot"])
    def test_anything_that_is_not_a_path_element_raises(self, bad):
        with pytest.raises(ValueError):
            brightness.object_path(bad)


class TestParseProperties:
    def test_the_measured_output_is_read_completely(self):
        props = brightness.parse_properties(MEASURED)
        assert props == brightness.Properties(
            raw=10000, maximum=10000, label="Example Corp. XY27-1234", internal=False
        )

    def test_a_label_containing_a_colon_survives(self):
        # Getrennt wird am ERSTEN ": " — sonst verliert ein Modellname mit
        # Doppelpunkt seinen Rest.
        props = brightness.parse_properties(
            "Brightness: 5000\nIsInternal: true\nLabel: Dell Inc.: U2720Q\nMaxBrightness: 10000\n"
        )
        assert props is not None
        assert props.label == "Dell Inc.: U2720Q"
        assert props.internal is True

    @pytest.mark.parametrize(
        "output",
        [
            "IsInternal: false\nLabel: X\nMaxBrightness: 10000\n",  # Brightness fehlt
            "Brightness: 10\nIsInternal: false\nLabel: X\n",  # MaxBrightness fehlt
            "Brightness: viel\nIsInternal: false\nLabel: X\nMaxBrightness: 100\n",  # nicht Zahl
        ],
    )
    def test_an_incomplete_answer_is_none_not_a_guess(self, output):
        assert brightness.parse_properties(output) is None

    def test_a_maximum_of_zero_is_no_usable_display(self):
        # Ohne oberes Ende gibt es kein Prozent und keinen Zielwert. Ein
        # solcher Eintrag darf nicht als "0 %" in der Liste landen.
        assert brightness.parse_properties(
            "Brightness: 0\nIsInternal: false\nLabel: X\nMaxBrightness: 0\n"
        ) is None


class TestPercentConversion:
    @pytest.mark.parametrize(
        "raw,maximum,percent",
        [(10000, 10000, 100), (6000, 10000, 60), (0, 10000, 0), (12, 20, 60), (1, 3, 33)],
    )
    def test_raw_becomes_percent(self, raw, maximum, percent):
        assert brightness.to_percent(raw, maximum) == percent

    @pytest.mark.parametrize(
        "percent,maximum,raw",
        [(100, 10000, 10000), (60, 10000, 6000), (5, 10000, 500), (100, 20, 20), (5, 20, 1)],
    )
    def test_percent_becomes_raw(self, percent, maximum, raw):
        assert brightness.to_raw(percent, maximum) == raw

    def test_the_raw_value_never_leaves_the_device_range(self):
        # Die Route begrenzt bereits auf 5..100; diese Klammer ist die zweite
        # Haelfte davon und haelt auch, wenn jemand das Modell aendert.
        assert brightness.to_raw(140, 10000) == 10000
        assert brightness.to_raw(-20, 10000) == 0


class TestRunQdbus:
    # Wie in TestRunKscreen: wayland_session_env() liest os.getuid() und wird
    # ausgewertet, bevor das gepatchte subprocess.run laeuft. Gegenstand hier
    # ist die Fehlerbehandlung des Runners, nicht der Umgebungs-Helfer.
    @pytest.fixture(autouse=True)
    def _stub_session_env(self):
        with patch.object(brightness, "wayland_session_env", return_value={}):
            yield

    def test_a_missing_binary_is_reported_not_raised(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            ok, message = brightness.run_qdbus(["x"])
        assert ok is False
        assert brightness.QDBUS_BINARY in message

    def test_a_timeout_is_reported_not_raised(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("x", 10)):
            ok, _ = brightness.run_qdbus(["x"])
        assert ok is False

    def test_a_nonzero_exit_is_a_failure(self):
        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        with patch("subprocess.run", return_value=completed):
            ok, message = brightness.run_qdbus(["x"])
        assert ok is False
        assert message == "boom"

    def test_noise_on_stderr_does_not_spoil_a_successful_call(self):
        # Gemessen: qdbus6 schreibt bei einem Locale ohne UTF-8 vier Zeilen
        # Warnung nach stderr und liefert trotzdem rc=0. Wer stderr als
        # Fehlersignal nimmt, verliert hier jeden Wert.
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="10000\n", stderr='Detected locale "C" ...'
        )
        with patch("subprocess.run", return_value=completed):
            ok, message = brightness.run_qdbus(["x"])
        assert (ok, message) == (True, "10000")

    def test_the_call_always_carries_a_timeout_and_never_a_shell(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        with patch("subprocess.run", return_value=completed) as run:
            brightness.run_qdbus(["x"])
        assert run.call_args.kwargs["timeout"] == brightness.QDBUS_TIMEOUT_SECONDS
        assert run.call_args.kwargs.get("shell") in (None, False)


class TestReadDisplays:
    def test_the_measured_session_yields_one_display(self):
        with patch.object(brightness, "run_qdbus", side_effect=[(True, MEASURED_IDS), (True, MEASURED)]):
            displays = brightness.read_displays()
        assert displays == [
            brightness.DisplayBrightness(
                id="display13",
                label="Example Corp. XY27-1234",
                internal=False,
                raw=10000,
                maximum=10000,
            )
        ]

    def test_an_unreachable_service_is_none_not_an_empty_list(self):
        # None heisst "nicht erreichbar", [] heisst "erreichbar, aber nichts
        # steuerbar". Die UI zeigt beides verschieden an.
        with patch.object(brightness, "run_qdbus", return_value=(False, "boom")):
            assert brightness.read_displays() is None

    def test_no_controllable_display_is_an_empty_list(self):
        with patch.object(brightness, "run_qdbus", return_value=(True, "")):
            assert brightness.read_displays() == []

    def test_one_broken_display_does_not_lose_the_others(self):
        with patch.object(
            brightness,
            "run_qdbus",
            side_effect=[(True, "display13\ndisplay7\n"), (False, "weg"), (True, MEASURED)],
        ):
            displays = brightness.read_displays()
        assert [d.id for d in displays] == ["display7"]

    def test_an_empty_label_falls_back_to_the_id(self):
        # Ein leerer Name ergaebe im Popover einen Regler ohne Beschriftung.
        props = "Brightness: 10000\nIsInternal: false\nLabel: \nMaxBrightness: 10000\n"
        with patch.object(brightness, "run_qdbus", side_effect=[(True, "display13\n"), (True, props)]):
            displays = brightness.read_displays()
        assert displays[0].label == "display13"


class TestWriteBrightness:
    def test_the_write_addresses_the_object_and_passes_the_neutral_flag(self):
        with patch.object(brightness, "run_qdbus", return_value=(True, "")) as run:
            ok, _ = brightness.write_brightness("display13", 6000)
        assert ok is True
        assert run.call_args.args[0] == [
            "org.kde.ScreenBrightness",
            "/org/kde/ScreenBrightness/display13",
            "org.kde.ScreenBrightness.Display.SetBrightness",
            "6000",
            "0",
        ]

    def test_an_id_that_never_appeared_in_an_enumeration_raises(self):
        # Doppelte Sicherung: der Service prueft die ID gegen die
        # Live-Enumeration, und object_path() laesst ohnehin nur
        # Pfadbestandteile durch.
        with pytest.raises(ValueError):
            brightness.write_brightness("../../evil", 5000)
