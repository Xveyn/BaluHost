"""Validierung: kein Wert wird zum Argument, der nicht enumeriert wurde."""
import pytest

from app.plugins.installed.display_output.backend import DevDisplayBackend
from app.plugins.installed.display_output.models import DisplayApplyRequest
from app.plugins.installed.display_output.service import (
    DisplayService,
    DisplayUnavailable,
    InvalidRequest,
    ModeMismatch,
)


def _req(outputs: list) -> DisplayApplyRequest:
    return DisplayApplyRequest(outputs=outputs)


@pytest.fixture
def service() -> DisplayService:
    return DisplayService(backend=DevDisplayBackend())


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_a_valid_change_is_applied(self, service):
        ok, _ = await service.apply(_req([
            {"name": "HDMI-A-1", "selected": True, "mode_id": "1", "mode_name": "2560x1440@144"},
            {"name": "DP-3", "selected": False},
        ]))
        assert ok is True
        layout = await service.get_layout()
        assert {o.name: o.selected for o in layout.outputs} == {"HDMI-A-1": True, "DP-3": False}

    @pytest.mark.asyncio
    async def test_selecting_without_a_mode_keeps_the_current_one(self, service):
        ok, _ = await service.apply(_req([{"name": "DP-3", "selected": True}]))
        assert ok is True
        dp3 = next(o for o in (await service.get_layout()).outputs if o.name == "DP-3")
        assert dp3.current_mode_id == "57"


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
            ok, _ = await service.apply(_req([{
                "name": "DP-3", "selected": True,
                "mode_id": mode_id, "mode_name": "3840x2160@120",
            }]))
            assert ok is True
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
        ok, _ = await service.apply(_req([{"name": "HDMI-A-1", "selected": False}]))
        assert ok is True

    @pytest.mark.asyncio
    async def test_a_mode_on_a_deselected_output_is_ignored_not_rejected(self, service):
        ok, _ = await service.apply(_req([{
            "name": "HDMI-A-1", "selected": False,
            "mode_id": "1", "mode_name": "2560x1440@144",
        }]))
        assert ok is True


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
