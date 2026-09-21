"""The icon set must be complete — a missing file means an invisible tray."""

from pathlib import Path

import pytest

from baluhost_tray.icons import SIZES, icon_path
from baluhost_tray.state import IconState


@pytest.mark.parametrize("state", list(IconState))
@pytest.mark.parametrize("size", SIZES)
def test_icon_exists_for_every_state_and_size(state: IconState, size: int):
    path = icon_path(state, size)
    assert path.exists(), f"fehlt: {path}"
    assert path.stat().st_size > 0


def test_unknown_size_falls_back_to_the_smallest():
    assert icon_path(IconState.OK, 17) == icon_path(IconState.OK, 22)


def test_icons_ship_inside_the_package():
    """Sie muessen neben dem Modul liegen, nicht irgendwo im Repo — sonst
    fehlen sie im installierten Paket."""
    from baluhost_tray import icons as icons_pkg

    package_dir = Path(icons_pkg.__file__).parent
    assert icon_path(IconState.OK, 22).parent == package_dir
