"""Cross-worker plugin enablement: the DB-backed cache (#448)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import plugin_enablement as pe


@pytest.fixture(autouse=True)
def _clean_cache():
    pe.invalidate()
    yield
    pe.invalidate()


class TestCache:
    async def test_refresh_loads_names_and_permissions(self):
        with patch.object(pe, "_fetch", return_value={"demo": ["files.read"]}):
            await pe.refresh()
        assert pe.enabled_plugins() == {"demo": ["files.read"]}
        assert pe.is_enabled("demo") is True
        assert pe.is_enabled("other") is False

    async def test_second_refresh_inside_the_ttl_does_not_hit_the_db(self):
        with patch.object(pe, "_fetch", return_value={"demo": []}) as fetch:
            await pe.refresh()
            await pe.refresh()
        assert fetch.call_count == 1

    async def test_refresh_after_the_ttl_hits_the_db_again(self, monkeypatch):
        clock = {"now": 1000.0}
        monkeypatch.setattr(pe, "_monotonic", lambda: clock["now"])
        with patch.object(pe, "_fetch", return_value={"demo": []}) as fetch:
            await pe.refresh()
            clock["now"] += pe.CACHE_TTL_SECONDS + 0.1
            await pe.refresh()
        assert fetch.call_count == 2

    async def test_force_bypasses_the_ttl(self):
        with patch.object(pe, "_fetch", return_value={"demo": []}) as fetch:
            await pe.refresh()
            await pe.refresh(force=True)
        assert fetch.call_count == 2

    async def test_db_error_propagates_instead_of_being_swallowed(self):
        """The two callers must fail in opposite directions, so the helper
        does not get to decide - it hands the failure up."""
        with patch.object(pe, "_fetch", side_effect=RuntimeError("db down")):
            with pytest.raises(RuntimeError):
                await pe.refresh()

    async def test_stale_cache_survives_a_failed_refresh(self):
        with patch.object(pe, "_fetch", return_value={"demo": []}):
            await pe.refresh()
        with patch.object(pe, "_fetch", side_effect=RuntimeError("db down")):
            with pytest.raises(RuntimeError):
                await pe.refresh(force=True)
        assert pe.enabled_plugins() == {"demo": []}

    def test_no_data_before_the_first_refresh(self):
        assert pe.enabled_plugins() is None
        assert pe.is_enabled("demo") is None

    async def test_sync_readers_never_touch_the_db(self):
        """Pinned because get_all_plugins() has no session to give them."""
        with patch.object(pe, "_fetch", return_value={"demo": []}):
            await pe.refresh()
        with patch.object(pe, "_fetch", side_effect=AssertionError("sync read hit the DB")):
            assert pe.is_enabled("demo") is True
            assert pe.enabled_plugins() == {"demo": []}

    async def test_invalidate_forces_the_next_refresh(self):
        with patch.object(pe, "_fetch", return_value={"demo": []}) as fetch:
            await pe.refresh()
            pe.invalidate()
            await pe.refresh()
        assert fetch.call_count == 2
