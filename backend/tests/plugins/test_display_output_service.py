"""Validierung: kein Wert wird zum Argument, der nicht enumeriert wurde."""
import pytest

from app.plugins.installed.display_output.backend import DevDisplayBackend
from app.plugins.installed.display_output.brightness import DisplayBrightness
from app.plugins.installed.display_output.models import (
    BrightnessRequest,
    DisplayApplyRequest,
    DisplayLayout,
)
from app.plugins.installed.display_output.service import (
    ApplyResult,
    DisplayService,
    DisplayUnavailable,
    InvalidRequest,
    ModeMismatch,
)


def _req(outputs: list) -> DisplayApplyRequest:
    return DisplayApplyRequest(outputs=outputs)


class _CoarseBrightness(DevDisplayBackend):
    """Ein Panel mit grober Skala — 20 Stufen statt 10000.

    Genau daran zeigt sich, ob die Prozentumrechnung wirklich die Geraeteskala
    benutzt: bei ``maximum == 100`` waere jeder Rechenfehler unsichtbar.
    """

    def __init__(self) -> None:
        super().__init__()
        self.written: tuple | None = None

    async def get_brightness(self):
        return [DisplayBrightness(id="d1", label="Grob", internal=False, raw=12, maximum=20)]

    async def set_brightness(self, display_id: str, raw: int):
        self.written = (display_id, raw)
        return True, "ok"


@pytest.fixture
def service() -> DisplayService:
    return DisplayService(backend=DevDisplayBackend())


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_a_valid_change_is_applied(self, service):
        result = await service.apply(_req([
            {"name": "HDMI-A-1", "selected": True, "mode_id": "1", "mode_name": "2560x1440@144"},
            {"name": "DP-3", "selected": False},
        ]))
        assert isinstance(result, ApplyResult)
        assert result.success is True
        layout = await service.get_layout()
        assert {o.name: o.selected for o in layout.outputs} == {"HDMI-A-1": True, "DP-3": False}

    @pytest.mark.asyncio
    async def test_selecting_without_a_mode_keeps_the_current_one(self, service):
        result = await service.apply(_req([{"name": "DP-3", "selected": True}]))
        assert result.success is True
        dp3 = next(o for o in (await service.get_layout()).outputs if o.name == "DP-3")
        assert dp3.current_mode_id == "57"


class TestApplyResultArgv:
    """Der argv-Vektor in ApplyResult ist der Gegenstand von Task 1.

    Er muss das abbilden, was der Service tatsaechlich geprueft (und bei
    KWinDisplayBackend an kscreen-doctor geschickt) hat — nicht die rohe
    Anfrage.
    """

    @pytest.mark.asyncio
    async def test_argv_carries_the_validated_change(self, service):
        result = await service.apply(_req([{
            "name": "HDMI-A-1", "selected": True,
            "mode_id": "1", "mode_name": "2560x1440@144",
        }]))
        assert result.argv == [
            "kscreen-doctor",
            "output.HDMI-A-1.enable",
            "output.HDMI-A-1.mode.1",
        ]

    @pytest.mark.asyncio
    async def test_a_mode_on_a_deselected_output_never_reaches_argv(self, service):
        # Der zentrale Fall aus Task 1: eine mode_id auf einem selected=false
        # -Ausgang wird vom Service verworfen (siehe Zeile "Bei selected=False
        # bleibt mode_id None") - sie darf deshalb auch nicht so aussehen, als
        # waere sie Teil des Vorgangs gewesen.
        result = await service.apply(_req([{
            "name": "HDMI-A-1", "selected": False,
            "mode_id": "1", "mode_name": "2560x1440@144",
        }]))
        assert result.argv == ["kscreen-doctor", "output.HDMI-A-1.disable"]


class TestWhitelist:
    @pytest.mark.asyncio
    async def test_an_unknown_output_is_rejected(self, service):
        with pytest.raises(InvalidRequest):
            await service.apply(_req([{"name": "DP-99", "selected": True}]))

    @pytest.mark.asyncio
    async def test_a_mode_belonging_to_another_output_is_rejected(self, service):
        # Das ist #589 als Testfall: Mode-IDs sind global vergeben, also
        # existiert "57" - aber nicht an HDMI-A-1.
        with pytest.raises(InvalidRequest):
            await service.apply(_req([{
                "name": "HDMI-A-1", "selected": True,
                "mode_id": "57", "mode_name": "3840x2160@120",
            }]))

    @pytest.mark.asyncio
    async def test_an_unknown_mode_id_is_rejected(self, service):
        with pytest.raises(InvalidRequest):
            await service.apply(_req([{
                "name": "DP-3", "selected": True, "mode_id": "9999", "mode_name": "x",
            }]))

    @pytest.mark.asyncio
    async def test_a_duplicate_output_in_one_request_is_rejected(self, service):
        with pytest.raises(InvalidRequest):
            await service.apply(_req([
                {"name": "DP-3", "selected": True},
                {"name": "DP-3", "selected": False},
            ]))


class TestModeCrossCheck:
    @pytest.mark.asyncio
    async def test_a_mode_id_without_a_name_is_rejected(self, service):
        # Sonst waere die Gegenprobe vom Client abschaltbar.
        with pytest.raises(InvalidRequest):
            await service.apply(_req([{"name": "DP-3", "selected": True, "mode_id": "58"}]))

    @pytest.mark.asyncio
    async def test_a_name_without_an_id_is_rejected(self, service):
        with pytest.raises(InvalidRequest):
            await service.apply(_req([{
                "name": "DP-3", "selected": True, "mode_name": "3840x2160@120",
            }]))

    @pytest.mark.asyncio
    async def test_a_stale_name_for_a_live_id_is_a_conflict(self, service):
        with pytest.raises(ModeMismatch):
            await service.apply(_req([{
                "name": "DP-3", "selected": True,
                "mode_id": "58", "mode_name": "1920x1080@60",
            }]))

    @pytest.mark.asyncio
    async def test_the_ambiguous_pair_is_addressable_member_by_member(self, service):
        # Beide heissen "3840x2160@120". Ueber die ID sind sie trotzdem
        # unterscheidbar - der ganze Punkt des Entwurfs.
        for mode_id in ("57", "58"):
            result = await service.apply(_req([{
                "name": "DP-3", "selected": True,
                "mode_id": mode_id, "mode_name": "3840x2160@120",
            }]))
            assert result.success is True
            dp3 = next(o for o in (await service.get_layout()).outputs if o.name == "DP-3")
            assert dp3.current_mode_id == mode_id


class TestInvariant:
    @pytest.mark.asyncio
    async def test_deselecting_every_connected_output_is_rejected(self, service):
        with pytest.raises(InvalidRequest):
            await service.apply(_req([
                {"name": "HDMI-A-1", "selected": False},
                {"name": "DP-3", "selected": False},
            ]))

    @pytest.mark.asyncio
    async def test_an_omitted_output_still_counts_as_selected(self, service):
        # DP-3 steht nicht im Request und bleibt gewaehlt - also ist das
        # Abwaehlen von HDMI-A-1 erlaubt.
        result = await service.apply(_req([{"name": "HDMI-A-1", "selected": False}]))
        assert result.success is True

    @pytest.mark.asyncio
    async def test_a_mode_on_a_deselected_output_is_ignored_not_rejected(self, service):
        result = await service.apply(_req([{
            "name": "HDMI-A-1", "selected": False,
            "mode_id": "1", "mode_name": "2560x1440@144",
        }]))
        assert result.success is True
        # Task 1: der geprueften argv-Vektor enthaelt keinen Modus fuer einen
        # abgewaehlten Ausgang - der Service verwirft diese Kombination beim
        # Aufbau von `wanted`, und der Audit-Eintrag darf nur berichten, was
        # tatsaechlich geprueft wurde.
        assert not any("mode" in arg for arg in result.argv if "HDMI-A-1" in arg)


class TestUnavailable:
    @pytest.mark.asyncio
    async def test_an_unreachable_session_raises_before_anything_is_applied(self):
        from app.plugins.installed.display_output.models import DisplayLayout

        class _Dead:
            async def get_layout(self):
                return DisplayLayout(available=False, detail="KWin nicht erreichbar")

            async def apply(self, wanted, live_outputs):
                raise AssertionError("apply darf bei toter Session nicht laufen")

        dead = DisplayService(backend=_Dead())
        with pytest.raises(DisplayUnavailable):
            await dead.apply(_req([{"name": "DP-3", "selected": True}]))


class TestBrightnessRead:
    @pytest.mark.asyncio
    async def test_the_layout_carries_the_brightness_in_percent(self, service):
        layout = await service.get_layout()
        assert layout.brightness.available is True
        assert [d.percent for d in layout.brightness.displays] == [100]

    @pytest.mark.asyncio
    async def test_the_percent_comes_from_the_device_scale_not_from_the_raw_value(self):
        # Ein Panel mit 20 Stufen: 12 von 20 sind 60 %, nicht 12 %.
        service = DisplayService(backend=_CoarseBrightness())
        assert (await service.get_layout()).brightness.displays[0].percent == 60

    @pytest.mark.asyncio
    async def test_an_unreachable_brightness_service_does_not_kill_the_layout(self):
        # powerdevil kann fehlen, waehrend KWin laeuft. Dann bleiben die
        # Ausgaenge bedienbar und nur der Helligkeitsblock meldet sich ab.
        class _NoBrightness(DevDisplayBackend):
            async def get_brightness(self):
                return None

        layout = await DisplayService(backend=_NoBrightness()).get_layout()
        assert layout.available is True
        assert layout.brightness.available is False
        assert layout.brightness.displays == []

    @pytest.mark.asyncio
    async def test_a_dead_session_is_not_asked_for_brightness_at_all(self):
        # 1+n Unterprozesse an powerdevil brauchen bei toter Sitzung niemand:
        # das Popover zeigt in diesem Zustand nur den Sitzungshinweis.
        class _Dead:
            async def get_layout(self):
                return DisplayLayout(available=False, detail="KWin nicht erreichbar")

            async def get_brightness(self):
                raise AssertionError("bei toter Sitzung nicht fragen")

        layout = await DisplayService(backend=_Dead()).get_layout()
        assert layout.available is False


class TestBrightnessWrite:
    @pytest.mark.asyncio
    async def test_the_percent_is_converted_to_the_device_scale(self):
        backend = _CoarseBrightness()
        await DisplayService(backend=backend).set_brightness(BrightnessRequest(id="d1", percent=35))
        # 35 % von 20 Stufen sind 7 — die Umrechnung gehoert in den Service,
        # damit das Backend nur noch einen Geraetewert weiterreicht.
        assert backend.written == ("d1", 7)

    @pytest.mark.asyncio
    async def test_an_id_that_is_not_in_the_live_enumeration_is_rejected(self, service):
        # Der Kern der Absicherung: kein Wert wird zum D-Bus-Argument, der
        # nicht in der Enumeration DIESES Vorgangs stand.
        with pytest.raises(InvalidRequest):
            await service.set_brightness(BrightnessRequest(id="display99", percent=50))

    @pytest.mark.asyncio
    async def test_an_unreachable_service_raises_unavailable(self):
        class _NoBrightness(DevDisplayBackend):
            async def get_brightness(self):
                return None

            async def set_brightness(self, display_id, raw):
                raise AssertionError("ohne Enumeration nicht schreiben")

        with pytest.raises(DisplayUnavailable):
            await DisplayService(backend=_NoBrightness()).set_brightness(
                BrightnessRequest(id="display13", percent=50)
            )

    @pytest.mark.asyncio
    async def test_a_failing_write_is_reported_not_raised(self):
        class _Failing(_CoarseBrightness):
            async def set_brightness(self, display_id, raw):
                return False, "DDC verweigert"

        ok, message = await DisplayService(backend=_Failing()).set_brightness(
            BrightnessRequest(id="d1", percent=50)
        )
        assert ok is False
        assert message == "DDC verweigert"
