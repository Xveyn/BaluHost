from app.schemas.desktop import DesktopState, DesktopStatus


def test_desktop_state_enum_values():
    assert DesktopState.RUNNING.value == "running"
    assert DesktopState.STOPPED.value == "stopped"
    assert DesktopState.UNKNOWN.value == "unknown"


def test_desktop_status_defaults():
    s = DesktopStatus(state=DesktopState.RUNNING, display_manager="sddm")
    assert s.state is DesktopState.RUNNING
    assert s.display_manager == "sddm"
    assert s.detail is None
