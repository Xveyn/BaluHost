"""Parser-Tests gegen den gemessenen kscreen-doctor-Mitschnitt von BaluNode."""
import json
from pathlib import Path

import pytest

from app.plugins.installed.display_output.kscreen import parse_modes, parse_outputs

FIXTURE = Path(__file__).parent / "fixtures" / "kscreen_balunode.json"


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def outputs(payload):
    return parse_outputs(payload)


class TestOutputs:
    def test_lists_both_connected_outputs(self, outputs):
        assert [o.name for o in outputs] == ["HDMI-A-1", "DP-3"]

    def test_selected_mirrors_kwin_enabled(self, outputs):
        by_name = {o.name: o for o in outputs}
        assert by_name["DP-3"].selected is True
        assert by_name["HDMI-A-1"].selected is False

    def test_lit_is_unknown_until_the_drm_layer_is_merged(self, outputs):
        # Der Parser kennt sysfs nicht. None heisst "nicht beantwortet",
        # nicht "aus" - siehe Spec 5.
        assert all(o.lit is None for o in outputs)

    def test_current_and_preferred_are_mode_ids(self, outputs):
        by_name = {o.name: o for o in outputs}
        assert by_name["DP-3"].current_mode_id == "57"
        assert by_name["DP-3"].preferred_mode_id == "56"
        assert by_name["HDMI-A-1"].current_mode_id == "1"

    def test_scale_is_read(self, outputs):
        by_name = {o.name: o for o in outputs}
        assert by_name["DP-3"].scale == 2.5

    def test_a_missing_optional_field_does_not_break_the_parser(self, outputs):
        # DP-3 traegt kein vrrPolicy. Ein direkter Indexzugriff kippte hier.
        assert len(outputs) == 2


class TestModes:
    def test_exact_duplicates_collapse_and_distinct_rates_survive(self, outputs):
        hdmi = next(o for o in outputs if o.name == "HDMI-A-1")
        # 55 Roheintraege, fuenf exakte Dubletten fallen weg.
        assert len(hdmi.modes) == 50

    def test_the_collapsed_duplicate_keeps_the_lower_id(self, outputs):
        hdmi = next(o for o in outputs if o.name == "HDMI-A-1")
        fullhd_60 = [
            m for m in hdmi.modes
            if m.width == 1920 and m.height == 1080 and round(m.refresh_rate, 2) == 60.0
        ]
        assert len(fullhd_60) == 1
        assert fullhd_60[0].id == "9"

    def test_the_120hz_pair_is_kept_apart(self, outputs):
        dp3 = next(o for o in outputs if o.name == "DP-3")
        uhd = [m for m in dp3.modes if m.width == 3840 and m.height == 2160]
        rates = sorted(round(m.refresh_rate, 2) for m in uhd if round(m.refresh_rate, 2) >= 119)
        assert rates == [119.88, 120.0]

    def test_both_of_the_pair_carry_the_same_ambiguous_name(self, outputs):
        dp3 = next(o for o in outputs if o.name == "DP-3")
        pair = {m.id: m.name for m in dp3.modes if m.id in ("57", "58")}
        assert pair == {"57": "3840x2160@120", "58": "3840x2160@120"}

    def test_modes_are_sorted_by_area_then_refresh_descending(self, outputs):
        dp3 = next(o for o in outputs if o.name == "DP-3")
        keys = [(-(m.width * m.height), -m.refresh_rate) for m in dp3.modes]
        assert keys == sorted(keys)

    def test_the_refresh_rate_is_not_rounded(self, outputs):
        dp3 = next(o for o in outputs if o.name == "DP-3")
        mode58 = next(m for m in dp3.modes if m.id == "58")
        assert mode58.refresh_rate == pytest.approx(119.87999725, rel=1e-9)


class TestParseModesInIsolation:
    def test_a_mode_without_size_is_skipped(self):
        modes = parse_modes([
            {"id": "1", "name": "1920x1080@60", "refreshRate": 60,
             "size": {"width": 1920, "height": 1080}},
            {"id": "2", "name": "broken"},
        ])
        assert [m.id for m in modes] == ["1"]

    def test_an_empty_list_yields_no_modes(self):
        assert parse_modes([]) == []


class TestCollapsedCurrentModeRemap:
    """currentModeId/preferredModes[0] duerfen nie auf eine kollabierte ID zeigen.

    parse_modes fasst exakte Dubletten zusammen und behaelt die kleinere ID.
    Zeigt KWins currentModeId (oder preferredModes[0]) auf die groessere,
    verworfene ID des Paars, existiert diese ID in der zurueckgegebenen
    Modenliste nicht mehr - das Frontend-Auswahlfeld (`value={entry.modeId
    ?? ''}`) trifft dann kein <option> und zeigt keine aktuelle Aufloesung.
    """

    @staticmethod
    def _payload(current_mode_id=None, preferred_modes=None) -> dict:
        output = {
            "name": "HDMI-A-1", "connected": True, "enabled": True,
            "modes": [
                {"id": "9", "name": "1920x1080@60", "refreshRate": 60,
                 "size": {"width": 1920, "height": 1080}},
                {"id": "10", "name": "1920x1080@60", "refreshRate": 60,
                 "size": {"width": 1920, "height": 1080}},
            ],
        }
        if current_mode_id is not None:
            output["currentModeId"] = current_mode_id
        if preferred_modes is not None:
            output["preferredModes"] = preferred_modes
        return {"outputs": [output]}

    def test_current_mode_id_remaps_to_the_surviving_duplicate(self):
        outputs = parse_outputs(self._payload(current_mode_id="10"))
        surviving_ids = [m.id for m in outputs[0].modes]
        assert outputs[0].current_mode_id == "9"
        assert outputs[0].current_mode_id in surviving_ids

    def test_preferred_mode_id_remaps_to_the_surviving_duplicate(self):
        outputs = parse_outputs(self._payload(preferred_modes=["10"]))
        surviving_ids = [m.id for m in outputs[0].modes]
        assert outputs[0].preferred_mode_id == "9"
        assert outputs[0].preferred_mode_id in surviving_ids

    def test_a_non_collapsed_current_mode_id_is_left_alone(self):
        outputs = parse_outputs(self._payload(current_mode_id="9"))
        assert outputs[0].current_mode_id == "9"
