"""Dev-Backend und die DRM-Verschmelzung des KWin-Backends."""
from unittest.mock import patch

import pytest

from app.plugins.installed.display_output.backend import DevDisplayBackend, KWinDisplayBackend
from app.plugins.installed.display_output.brightness import DisplayBrightness


class TestDevBackend:
    @pytest.mark.asyncio
    async def test_mirrors_balunode_with_two_connected_outputs(self):
        layout = await DevDisplayBackend().get_layout()
        assert [o.name for o in layout.outputs] == ["HDMI-A-1", "DP-3"]
        assert all(o.connected for o in layout.outputs)

    @pytest.mark.asyncio
    async def test_carries_the_ambiguous_120hz_pair(self):
        # Ohne diese Dublette laesst sich die Beschriftungslogik unter Windows
        # nicht bedienen - und genau sie ist der Grund fuer die ID-Adressierung.
        layout = await DevDisplayBackend().get_layout()
        dp3 = next(o for o in layout.outputs if o.name == "DP-3")
        names = [m.name for m in dp3.modes if m.name == "3840x2160@120"]
        assert len(names) == 2

    @pytest.mark.asyncio
    async def test_apply_changes_what_the_next_read_returns(self):
        backend = DevDisplayBackend()
        live = (await backend.get_layout()).outputs
        ok, _ = await backend.apply({"HDMI-A-1": (True, "1"), "DP-3": (False, None)}, live)
        assert ok is True
        after = {o.name: o for o in (await backend.get_layout()).outputs}
        assert after["HDMI-A-1"].selected is True
        assert after["DP-3"].selected is False
        assert after["HDMI-A-1"].current_mode_id == "1"

    @pytest.mark.asyncio
    async def test_lit_follows_selected_in_dev_mode(self):
        backend = DevDisplayBackend()
        layout = await backend.get_layout()
        for output in layout.outputs:
            assert output.lit == output.selected
        assert layout.displays_powered is True


class TestKWinBackend:
    @pytest.mark.asyncio
    async def test_an_unreachable_session_is_reported_not_raised(self):
        with patch(
            "app.plugins.installed.display_output.backend.run_kscreen_json", return_value=None
        ):
            layout = await KWinDisplayBackend().get_layout()
        assert layout.available is False
        assert layout.outputs == []

    @pytest.mark.asyncio
    async def test_merges_the_drm_layer_into_lit(self):
        payload = {"outputs": [{
            "name": "DP-3", "connected": True, "enabled": True, "currentModeId": "57",
            "modes": [{"id": "57", "name": "3840x2160@120", "refreshRate": 120,
                       "size": {"width": 3840, "height": 2160}}],
        }]}
        with patch(
            "app.plugins.installed.display_output.backend.run_kscreen_json", return_value=payload
        ), patch(
            "app.plugins.installed.display_output.backend.get_connector_states",
            return_value={"DP-3": True},
        ):
            layout = await KWinDisplayBackend().get_layout()
        assert layout.outputs[0].lit is True
        assert layout.displays_powered is True

    @pytest.mark.asyncio
    async def test_an_unmappable_output_stays_unknown_not_dark(self):
        payload = {"outputs": [{
            "name": "DP-9", "connected": True, "enabled": True,
            "modes": [{"id": "1", "name": "1920x1080@60", "refreshRate": 60,
                       "size": {"width": 1920, "height": 1080}}],
        }]}
        with patch(
            "app.plugins.installed.display_output.backend.run_kscreen_json", return_value=payload
        ), patch(
            "app.plugins.installed.display_output.backend.get_connector_states",
            return_value={"DP-3": True},
        ):
            layout = await KWinDisplayBackend().get_layout()
        assert layout.outputs[0].lit is None

    @pytest.mark.asyncio
    async def test_the_selection_is_dark_when_no_connector_is_lit(self):
        payload = {"outputs": [{
            "name": "DP-3", "connected": True, "enabled": True,
            "modes": [{"id": "1", "name": "1920x1080@60", "refreshRate": 60,
                       "size": {"width": 1920, "height": 1080}}],
        }]}
        with patch(
            "app.plugins.installed.display_output.backend.run_kscreen_json", return_value=payload
        ), patch(
            "app.plugins.installed.display_output.backend.get_connector_states",
            return_value={"DP-3": False},
        ):
            layout = await KWinDisplayBackend().get_layout()
        # Genau der Zustand, der DesktopTogglePanel "Gestoppt" melden laesst,
        # waehrend KWin DP-3 fuer gewaehlt haelt. Kein Widerspruch, zwei Ebenen.
        assert layout.outputs[0].selected is True
        assert layout.outputs[0].lit is False
        assert layout.displays_powered is False


class TestDevBackendBrightness:
    @pytest.mark.asyncio
    async def test_offers_one_controllable_display_although_two_outputs_exist(self):
        # Gemessen auf BaluNode: zwei verbundene Ausgaenge, aber nur EIN
        # Helligkeitsobjekt — powerdevil meldet nur eingeschaltete, steuerbare
        # Bildschirme. Ein Dev-Backend mit zwei Reglern behauptete einen
        # Zustand, den das echte nie liefert.
        displays = await DevDisplayBackend().get_brightness()
        assert len(displays) == 1
        assert displays[0].percent == 100

    @pytest.mark.asyncio
    async def test_the_object_id_is_not_an_output_name(self):
        # powerdevil vergibt eigene, fluechtige Objektnamen. Wer hier
        # "HDMI-A-1" einsetzt, baut eine Zuordnung, die die API nicht hergibt.
        displays = await DevDisplayBackend().get_brightness()
        assert displays[0].id not in {"HDMI-A-1", "DP-3"}

    @pytest.mark.asyncio
    async def test_a_write_changes_what_the_next_read_returns(self):
        backend = DevDisplayBackend()
        target = (await backend.get_brightness())[0]
        ok, _ = await backend.set_brightness(target.id, 6000)
        assert ok is True
        assert (await backend.get_brightness())[0].raw == 6000

    @pytest.mark.asyncio
    async def test_an_unknown_id_is_reported_not_raised(self):
        ok, _ = await DevDisplayBackend().set_brightness("display99", 5000)
        assert ok is False


class TestKWinBackendBrightness:
    @pytest.mark.asyncio
    async def test_the_module_answer_is_passed_through_unchanged(self):
        measured = [
            DisplayBrightness(
                id="display13", label="Example Corp. XY27-1234",
                internal=False, raw=10000, maximum=10000,
            )
        ]
        with patch(
            "app.plugins.installed.display_output.backend.read_displays", return_value=measured
        ):
            assert await KWinDisplayBackend().get_brightness() == measured

    @pytest.mark.asyncio
    async def test_an_unreachable_service_stays_none(self):
        # None heisst "keine Auskunft", [] heisst "nichts steuerbar". Das
        # Backend darf das eine nicht zum anderen machen.
        with patch(
            "app.plugins.installed.display_output.backend.read_displays", return_value=None
        ):
            assert await KWinDisplayBackend().get_brightness() is None

    @pytest.mark.asyncio
    async def test_the_raw_value_reaches_the_module_unchanged(self):
        # Umgerechnet wird im Service; das Backend rechnet nicht mit.
        with patch(
            "app.plugins.installed.display_output.backend.write_brightness",
            return_value=(True, ""),
        ) as write:
            await KWinDisplayBackend().set_brightness("display13", 6000)
        assert write.call_args.args == ("display13", 6000)
