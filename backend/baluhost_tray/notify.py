"""Desktop notifications via org.freedesktop.Notifications.

Going through the standard interface rather than a toolkit call is what makes
Plasma's own Do-Not-Disturb and fullscreen rules apply for free — the tray
does not have to detect anything itself.
"""

from __future__ import annotations

from baluhost_tray.icons import icon_path
from baluhost_tray.state import IconState, PendingPopup

_BUS_NAME = "org.freedesktop.Notifications"
_BUS_PATH = "/org/freedesktop/Notifications"
_APP_NAME = "BaluHost"
_TIMEOUT_MS = 10_000
# A path, not a theme name. The spec allows either, but the icons live inside
# this package and are never installed into an icon theme — the name
# "baluhost" resolved to nothing and Plasma drew an empty placeholder. The OK
# artwork is the brand icon; its green badge is the one compromise, since no
# badge-free file exists and PendingPopup carries no severity.
_ICON_URI = icon_path(IconState.OK, 48).as_uri()


class NotifierUnavailable(Exception):
    """No session bus or no notification server — e.g. started outside Plasma."""


class Notifier:
    def __init__(self) -> None:
        self._iface = None

    async def connect(self, _bus_factory=None) -> None:
        """Attach to the session bus.

        _bus_factory exists for the tests: it lets them drive the failure
        path without a bus and without patching module internals.
        """
        try:
            if _bus_factory is not None:
                bus = _bus_factory()
            else:
                from dbus_next import BusType
                from dbus_next.aio import MessageBus

                bus = await MessageBus(bus_type=BusType.SESSION).connect()

            introspection = await bus.introspect(_BUS_NAME, _BUS_PATH)
            obj = bus.get_proxy_object(_BUS_NAME, _BUS_PATH, introspection)
            self._iface = obj.get_interface(_BUS_NAME)
        except Exception as exc:
            raise NotifierUnavailable(str(exc)) from exc

    async def show(self, popup: PendingPopup) -> int:
        """Show one notification, return the server's id."""
        return await self._notify(popup.title, popup.message)

    async def show_summary(self, title: str, message: str) -> int:
        """Show the collapsed form used after a gaming session or quiet hour."""
        return await self._notify(title, message)

    async def _notify(self, title: str, message: str) -> int:
        if self._iface is None:
            raise NotifierUnavailable("not connected to a session bus")
        return await self._iface.call_notify(
            _APP_NAME,
            0,               # replaces_id: 0 = new notification
            _ICON_URI,
            title,
            message,
            [],              # actions
            {},              # hints
            _TIMEOUT_MS,
        )
