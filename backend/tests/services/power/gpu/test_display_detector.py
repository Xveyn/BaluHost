"""Test sysfs DRM connector counting."""
from pathlib import Path
import pytest

from app.services.power.gpu.display_detector import get_active_display_count


@pytest.fixture
def fake_sysfs(tmp_path: Path) -> Path:
    """Build a fake /sys/class/drm tree."""
    drm = tmp_path / "sys" / "class" / "drm"
    drm.mkdir(parents=True)
    return tmp_path


def _make_connector(root: Path, name: str, status: str, enabled: str) -> None:
    drm = root / "sys" / "class" / "drm"
    conn = drm / name
    conn.mkdir(parents=True, exist_ok=True)
    (conn / "status").write_text(status + "\n")
    (conn / "enabled").write_text(enabled + "\n")


@pytest.mark.asyncio
async def test_no_drm_directory(tmp_path: Path):
    count = await get_active_display_count(sysfs_root=tmp_path)
    assert count == 0


@pytest.mark.asyncio
async def test_no_connectors(fake_sysfs: Path):
    count = await get_active_display_count(sysfs_root=fake_sysfs)
    assert count == 0


@pytest.mark.asyncio
async def test_one_connected_display(fake_sysfs: Path):
    _make_connector(fake_sysfs, "card0-HDMI-A-1", "connected", "enabled")
    count = await get_active_display_count(sysfs_root=fake_sysfs)
    assert count == 1


@pytest.mark.asyncio
async def test_disconnected_display_not_counted(fake_sysfs: Path):
    _make_connector(fake_sysfs, "card0-HDMI-A-1", "disconnected", "disabled")
    count = await get_active_display_count(sysfs_root=fake_sysfs)
    assert count == 0


@pytest.mark.asyncio
async def test_connected_but_disabled_not_counted(fake_sysfs: Path):
    """DPMS-off / unused: don't count as active."""
    _make_connector(fake_sysfs, "card0-DP-1", "connected", "disabled")
    count = await get_active_display_count(sysfs_root=fake_sysfs)
    assert count == 0


@pytest.mark.asyncio
async def test_card_root_not_counted(fake_sysfs: Path):
    """`card0` itself (no -CONNECTOR suffix) is not a connector."""
    drm = fake_sysfs / "sys" / "class" / "drm"
    (drm / "card0").mkdir()
    count = await get_active_display_count(sysfs_root=fake_sysfs)
    assert count == 0


@pytest.mark.asyncio
async def test_multiple_connectors(fake_sysfs: Path):
    _make_connector(fake_sysfs, "card0-HDMI-A-1", "connected", "enabled")
    _make_connector(fake_sysfs, "card0-DP-1", "disconnected", "disabled")
    _make_connector(fake_sysfs, "card0-DP-2", "connected", "enabled")
    count = await get_active_display_count(sysfs_root=fake_sysfs)
    assert count == 2
