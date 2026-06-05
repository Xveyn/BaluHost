"""Tests for the game library aggregation service."""

from app.schemas.games import GameEntry, GameLibrary
from app.services.game_libraries import service


class _FakeProvider:
    id = "fake"
    name = "Fake"

    def __init__(self, available: bool, libs):
        self._available = available
        self._libs = libs

    def is_available(self) -> bool:
        return self._available

    def get_libraries(self):
        return self._libs


def _lib(total: int) -> GameLibrary:
    return GameLibrary(
        provider="fake", provider_name="Fake", path="/x", device_id=1,
        total_bytes=total, game_count=1,
        games=[GameEntry(app_id="1", name="g", size_bytes=total)],
    )


def test_aggregates_available_providers(monkeypatch):
    monkeypatch.setattr(service, "PROVIDERS", [_FakeProvider(True, [_lib(100), _lib(200)])])
    resp = service.get_game_libraries()
    assert resp.available is True
    assert resp.total_bytes == 300
    assert len(resp.libraries) == 2


def test_provider_exception_is_swallowed(monkeypatch):
    class Boom:
        id = "boom"; name = "Boom"
        def is_available(self): return True
        def get_libraries(self): raise RuntimeError("nope")
    monkeypatch.setattr(service, "PROVIDERS", [Boom()])
    resp = service.get_game_libraries()
    # The provider reported available before raising, so `available` stays True;
    # the exception is swallowed and yields no libraries (no mock masking it).
    assert resp.available is True
    assert resp.libraries == []


def test_dev_mock_when_no_real_libraries(monkeypatch):
    monkeypatch.setattr(service, "PROVIDERS", [_FakeProvider(False, [])])
    # Tests run with NAS_MODE=dev, so the mock kicks in.
    resp = service.get_game_libraries()
    assert resp.available is True
    assert len(resp.libraries) == 1
    assert resp.libraries[0].provider == "steam"
    assert resp.total_bytes == resp.libraries[0].total_bytes
