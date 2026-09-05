"""get_temperature loest stabile, praefixierte und Alt-IDs auf (#532)."""
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.power.fan_backend_linux import LinuxFanControlBackend


@pytest.fixture
def backend(tmp_path):
    hwmon = tmp_path / "hwmon3"
    hwmon.mkdir()
    (hwmon / "temp1_input").write_text("42000\n")
    be = LinuxFanControlBackend(get_settings())
    be._hwmon_base = tmp_path
    be._temp_paths = {"nct6798-isa-0290:temp1": hwmon / "temp1_input"}
    return be


@pytest.mark.asyncio
async def test_resolves_stable_id(backend):
    assert await backend.get_temperature("nct6798-isa-0290:temp1") == 42.0


@pytest.mark.asyncio
async def test_strips_hwmon_namespace_prefix(backend):
    assert await backend.get_temperature("hwmon:nct6798-isa-0290:temp1") == 42.0


@pytest.mark.asyncio
async def test_still_resolves_legacy_id(backend):
    # Waehrend der Umstellung stehen Alt-IDs noch in der Datenbank.
    assert await backend.get_temperature("hwmon3_temp1") == 42.0


@pytest.mark.asyncio
async def test_unknown_id_is_none(backend):
    assert await backend.get_temperature("nope-isa-0000:temp9") is None
