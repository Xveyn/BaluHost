"""Tests for game library schemas."""

from app.schemas.games import GameEntry, GameLibrary, GameLibrariesResponse


def test_schema_round_trip():
    lib = GameLibrary(
        provider="steam",
        provider_name="Steam",
        path="/mnt/cache-vcl/SteamLibrary",
        device_id=42,
        total_bytes=100,
        game_count=1,
        games=[GameEntry(app_id="730", name="CS2", size_bytes=100)],
    )
    resp = GameLibrariesResponse(libraries=[lib], total_bytes=100, available=True)
    dumped = resp.model_dump(mode="json")
    assert dumped["libraries"][0]["games"][0]["name"] == "CS2"
    assert dumped["available"] is True


def test_device_id_optional():
    lib = GameLibrary(
        provider="steam", provider_name="Steam", path="/x",
        total_bytes=0, game_count=0, games=[],
    )
    assert lib.device_id is None
