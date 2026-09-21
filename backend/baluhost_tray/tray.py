"""Qt surface. Rendering only — every decision lives in loop.py / state.py.

Nothing in here decides anything: no reconnect policy, no severity mapping, no
when-to-notify. Those live in state.py, watch.py and loop.py, where they are
tested without a display, a bus or a panel. What is left here is the panel
icon, the menu, and the thread boundary between asyncio and Qt.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

import websockets
from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from baluhost_tray.announce import QuietMode
from baluhost_tray.icons import SIZES, icon_path
from baluhost_tray.loop import LoopContext, is_gaming_active, run_loop
from baluhost_tray.notify import Notifier, NotifierUnavailable
from baluhost_tray.session import Session
from baluhost_tray.state import IconState, PopupQueue, TrayState
from baluhost_tray.watch import Watcher

logger = logging.getLogger(__name__)

MENU_OPEN = "BaluHost öffnen"
MENU_QUIET = "Eine Stunde stumm"
# Bewusst nicht "Neu koppeln": der Menuepunkt kann die Kopplung nicht selbst
# wiederherstellen — dafuer braucht es `baluhost-tray --pair` auf der Konsole.
# Er oeffnet die Geraeteseite, und der Name sagt genau das.
MENU_DEVICES = "Geräte in der Web-UI"
MENU_QUIT = "Beenden"
QUIET_SECONDS = 3600.0


class _Bridge(QObject):
    """Carries worker-thread results into the GUI thread.

    A cross-thread signal is a QueuedConnection by default, which is the only
    correct way to touch a QSystemTrayIcon from asyncio. The worker never
    calls setIcon itself.
    """

    state_changed = pyqtSignal(str)   # IconState.value
    tooltip_changed = pyqtSignal(str)
    fatal = pyqtSignal(str)           # Worker kann nicht weitermachen


def _build_icons() -> dict[IconState, QIcon]:
    """One QIcon per state, all sizes inside it.

    Plasma picks the right size itself on HiDPI panels; handing it only the
    22 px file would make it upscale that one.
    """
    icons: dict[IconState, QIcon] = {}
    for state in IconState:
        icon = QIcon()
        for size in SIZES:
            icon.addFile(str(icon_path(state, size)))
        icons[state] = icon
    return icons


def run_tray(base_url: str, web_url: str) -> int:
    """Start the Qt loop with the asyncio work on a worker thread.

    base_url is the API (FastAPI port), web_url is what a human should see —
    behind nginx those are different, and opening :8000 in a browser shows
    the API, not the UI.
    """
    app = QApplication([])
    app.setApplicationName("BaluHost")
    app.setQuitOnLastWindowClosed(False)

    # Spec-Fehlerfall 5, zweite Haelfte: kein SNI-Host. Synchron pruefbar,
    # anders als der Bus — deshalb hier und nicht im Worker.
    if not QSystemTrayIcon.isSystemTrayAvailable():
        raise NotifierUnavailable("no system tray in this session")

    icons = _build_icons()
    state = TrayState()
    queue = PopupQueue()
    quiet = QuietMode()

    tray_icon = QSystemTrayIcon(icons[IconState.OFFLINE])
    tray_icon.setToolTip(state.tooltip())

    bridge = _Bridge()
    bridge.state_changed.connect(
        lambda value: tray_icon.setIcon(icons[IconState(value)])
    )
    bridge.tooltip_changed.connect(tray_icon.setToolTip)

    def _open_web() -> None:
        QDesktopServices.openUrl(QUrl(web_url))

    menu = QMenu()
    menu.addAction(MENU_OPEN).triggered.connect(_open_web)

    quiet_action = menu.addAction(MENU_QUIET)
    quiet_action.setCheckable(True)

    # Ohne diesen Timer bliebe der Haken nach Ablauf der Stunde stehen und das
    # Menue behauptete "stumm", waehrend QuietMode laengst wieder zustellt.
    # Reine Anzeigepflege: die Frist selbst steht in QuietMode.
    quiet_timer = QTimer()
    quiet_timer.setSingleShot(True)
    quiet_timer.timeout.connect(lambda: quiet_action.setChecked(False))

    def _toggle_quiet(checked: bool) -> None:
        if checked:
            quiet.mute_for(QUIET_SECONDS, time.monotonic())
            quiet_timer.start(int(QUIET_SECONDS * 1000))
        else:
            quiet_timer.stop()
            quiet.clear()

    quiet_action.toggled.connect(_toggle_quiet)

    menu.addAction(MENU_DEVICES).triggered.connect(
        lambda: QDesktopServices.openUrl(QUrl(f"{web_url}/devices"))
    )
    menu.addSeparator()
    menu.addAction(MENU_QUIT).triggered.connect(app.quit)
    tray_icon.setContextMenu(menu)

    # Spec, Nicht-Ziele: "Ein Klick auf das Icon oeffnet die Web-UI."
    tray_icon.activated.connect(
        lambda reason: _open_web()
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    tray_icon.show()

    session = Session(base_url)
    notifier = Notifier()

    def _sink(icon_state: IconState) -> None:
        # Laeuft im Worker-Thread: nur Signale, kein Qt-Objekt direkt.
        bridge.state_changed.emit(icon_state.value)
        bridge.tooltip_changed.emit(state.tooltip())

    def _fatal(message: str) -> None:
        # Ohne diesen Weg stirbt der Worker still und das Tray steht fuer
        # immer auf grau, ohne dass jemand erfaehrt warum.
        print(message)
        app.quit()

    bridge.fatal.connect(_fatal)

    async def _main() -> None:
        try:
            await notifier.connect()
        except NotifierUnavailable as exc:
            bridge.fatal.emit(
                f"Keine Desktop-Benachrichtigungen verfügbar: {exc}"
            )
            return

        ctx = LoopContext(
            session=session,
            watcher=Watcher(session, state),
            state=state,
            queue=queue,
            notifier=notifier,
            sink=_sink,
            hold_probe=lambda: is_gaming_active(session.client()),
            connect=websockets.connect,
            quiet=quiet,
        )
        try:
            await run_loop(ctx)
        except Exception as exc:
            # asyncio.run() in einem Thread wuerde den Traceback nach stderr
            # schreiben und den Thread beenden; das Icon bliebe grau ohne
            # Erklaerung. Der Weg nach draussen geht ueber das Signal.
            logger.exception("tray worker stopped unexpectedly")
            bridge.fatal.emit(f"Tray-Hintergrund beendet: {exc}")

    threading.Thread(target=lambda: asyncio.run(_main()), daemon=True).start()
    return app.exec()
