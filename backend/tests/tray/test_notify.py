"""Tests for desktop notifications — against a stub bus, never a real one."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from baluhost_tray.notify import Notifier, NotifierUnavailable
from baluhost_tray.state import PendingPopup


def _stub_interface() -> MagicMock:
    iface = MagicMock()
    iface.call_notify = AsyncMock(return_value=42)
    return iface


@pytest.mark.asyncio
async def test_show_passes_title_and_message():
    notifier = Notifier()
    notifier._iface = _stub_interface()

    result = await notifier.show(
        PendingPopup(notification_id=1, title="RAID", message="degradiert")
    )

    assert result == 42
    args = notifier._iface.call_notify.await_args[0]
    assert "RAID" in args and "degradiert" in args


@pytest.mark.asyncio
async def test_show_without_connection_raises():
    with pytest.raises(NotifierUnavailable):
        await Notifier().show(PendingPopup(notification_id=1, title="x", message="y"))


@pytest.mark.asyncio
async def test_summary_is_one_message():
    notifier = Notifier()
    notifier._iface = _stub_interface()
    await notifier.show_summary("BaluHost", "4 neue kritische Meldungen")
    assert notifier._iface.call_notify.await_count == 1


@pytest.mark.asyncio
async def test_connect_without_a_bus_raises_the_typed_error():
    """Start ausserhalb von Plasma darf keinen rohen dbus-Fehler durchreichen."""
    notifier = Notifier()
    with pytest.raises(NotifierUnavailable):
        await notifier.connect(_bus_factory=lambda: (_ for _ in ()).throw(OSError("no bus")))
