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
from queue import Empty, Full, Queue    # NICHT `import queue`: run_tray() hat
                                         # schon eine lokale Variable `queue`
                                         # (PopupQueue) — ein Modulimport wuerde
                                         # `queue.Queue(...)` darauf aufloesen.

import websockets
from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QApplication, QInputDialog, QLineEdit, QMenu, QMessageBox, QSystemTrayIcon,
)

from baluhost_tray import config as tray_config
from baluhost_tray.announce import QuietMode
from baluhost_tray.icons import SIZES, icon_path
from baluhost_tray.loop import LoopContext, is_gaming_active, run_loop
from baluhost_tray.notify import Notifier, NotifierUnavailable
from baluhost_tray.restart import (
    RestartOutcome,
    fetch_account_facts,
    menu_visible,
    restart_flow,
)
from baluhost_tray.session import Session
from baluhost_tray.state import IconState, PopupQueue, TrayState
from baluhost_tray.watch import Watcher
from baluhost_tui.client import BackendClient

logger = logging.getLogger(__name__)

MENU_OPEN = "BaluHost öffnen"
MENU_QUIET = "Eine Stunde stumm"
# Bewusst nicht "Neu koppeln": der Menuepunkt kann die Kopplung nicht selbst
# wiederherstellen — dafuer braucht es `baluhost-tray --pair` auf der Konsole.
# Er oeffnet die Geraeteseite, und der Name sagt genau das.
MENU_DEVICES = "Geräte in der Web-UI"
MENU_RESTART = "BaluHost neu starten…"
MENU_QUIT = "Beenden"
QUIET_SECONDS = 3600.0
PROMPT_TIMEOUT = 300.0      # der Worker wartet nicht ewig auf einen Dialog


class _Bridge(QObject):
    """Carries worker-thread results into the GUI thread.

    A cross-thread signal is a QueuedConnection by default, which is the only
    correct way to touch a QSystemTrayIcon from asyncio. The worker never
    calls setIcon itself.
    """

    state_changed = pyqtSignal(str)   # IconState.value
    tooltip_changed = pyqtSignal(str)
    fatal = pyqtSignal(str)           # Worker kann nicht weitermachen
    restart_prompt = pyqtSignal(str)
    restart_finished = pyqtSignal(bool, str)
    restart_visible = pyqtSignal(bool)


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

    restart_action = menu.addAction(MENU_RESTART)
    # Bis die Rolle bekannt ist sichtbar: unbekannt heisst, dass die API gerade
    # nicht antwortet — genau der Fall, fuer den der Notweg da ist. Das Gate
    # ist polkit bzw. das Backend, nicht diese Zeile.
    restart_action.setVisible(True)
    bridge.restart_visible.connect(restart_action.setVisible)

    # Die Antwort des Dialogs geht ueber eine Queue zurueck in den
    # Arbeitsthread. Dialoge gehoeren in den GUI-Thread, Netzwerk nicht.
    answers: Queue = Queue(maxsize=1)

    def _show_prompt(mode: str) -> None:
        # Jeder Pfad legt genau eine Antwort ab. Ohne das finally bliebe der
        # Worker fuer immer in answers.get() haengen.
        value = None
        try:
            if mode == "local":
                choice = QMessageBox.question(
                    None,
                    "BaluHost neu starten",
                    "Das Backend antwortet nicht.\n\nDienste direkt über das "
                    "System neu starten? Das System fragt gleich nach dem "
                    "Passwort.\n\nLaufende Aufträge und Uploads werden dabei "
                    "abgebrochen.",
                )
                value = "ja" if choice == QMessageBox.StandardButton.Yes else None
                return
            is_totp = mode.startswith("totp")
            label = "2FA-Code" if is_totp else "Passwort"
            text = (
                f"{label} stimmt nicht. Noch einmal:"
                if mode.endswith("_retry")
                else f"{label} für BaluHost:\n\nLaufende Aufträge und Uploads "
                     f"werden abgebrochen."
            )
            typed, ok = QInputDialog.getText(
                None, "BaluHost neu starten", text, QLineEdit.EchoMode.Password
            )
            value = typed if ok and typed else None
        finally:
            # put_nowait, nicht put: laeuft der Worker laengst im
            # PROMPT_TIMEOUT (niemand liest answers.get() mehr) und wird
            # dieser verwaiste Dialog erst danach beantwortet, waere die
            # Queue noch leer und put() ginge durch — aber legt ein zweiter
            # verwaister Dialog nach, ohne dass ein Worker dazwischen
            # abgeholt hat, ist die Queue (maxsize=1) voll. Ein blockierendes
            # put() haengt dann den GUI-Thread komplett auf. Eine Antwort, die
            # niemand mehr erwartet, ist wertlos — verwerfen statt warten.
            try:
                answers.put_nowait(value)
            except Full:
                pass

    bridge.restart_prompt.connect(_show_prompt)

    def _restart_done(ok: bool, message: str) -> None:
        restart_action.setEnabled(True)
        box = QMessageBox.information if ok else QMessageBox.warning
        box(None, "BaluHost neu starten", message)

    bridge.restart_finished.connect(_restart_done)

    def _prompt_from_worker(mode: str) -> str | None:
        # Erst leeren, dann fragen: ein Rest aus einem verwaisten frueheren
        # Dialog (der Worker lief in den Timeout, wurde aber spaeter doch
        # noch beantwortet) darf nicht als Antwort auf *diesen* neuen Dialog
        # durchgehen — sonst startet dieser Versuch mit einem alten Passwort,
        # waehrend der gerade erst geoeffnete Dialog unbeantwortet bleibt.
        while True:
            try:
                answers.get_nowait()
            except Empty:
                break
        bridge.restart_prompt.emit(mode)
        try:
            return answers.get(timeout=PROMPT_TIMEOUT)
        except Empty:
            return None

    def _refresh_into(client: BackendClient) -> None:
        """Token erneuern und dem Neustart-Client mitgeben.

        `session.refresh_access()` schreibt in den Authorization-Header des
        gemeinsam genutzten Loop-Clients (`session.client()`), ueber
        `httpx.Headers.__setitem__` — das loescht den alten Eintrag und haengt
        den neuen an. Zwischen den beiden Schritten liegt eine Luecke: eine
        Anfrage, die der Loop im run_loop-Thread genau in diesem Moment
        aufbaut, kann ohne Header rausgehen. Harmlos, weil selbstheilend — ein
        401 daraus laesst den Loop selbst erneut refreshen. Alles, was beim
        Refresh hier schiefgeht, faengt restart.py ab — hier darf nichts durch.
        """
        session.refresh_access()
        tokens = tray_config.load_tokens()
        if tokens:
            client.set_token(tokens.access)

    def _restart_worker() -> None:
        outcome = RestartOutcome(False, "Unerwarteter Fehler.")
        client = None
        try:
            # Eigener Client: der Worker-Thread wechselt beim Refresh das Token
            # des gemeinsamen Clients, und zwei Threads auf demselben Objekt
            # sind eine Verabredung zum Rennen.
            tokens = tray_config.load_tokens()
            client = BackendClient(
                server=base_url, token=tokens.access if tokens else None
            )
            outcome = restart_flow(
                client,
                _prompt_from_worker,
                on_auth_expired=lambda: _refresh_into(client),
            )
        except Exception as exc:                     # noqa: BLE001
            logger.exception("restart flow failed")
            outcome = RestartOutcome(False, f"Unerwarteter Fehler: {exc}")
        finally:
            # client.close() darf das Signal nicht gefaehrden: schlaegt es
            # fehl, wuerde ein unbehandelter Fehler hier das finally
            # abbrechen und emit() nie erreichen — der Menuepunkt bliebe fuer
            # den Rest der Sitzung grau. Deshalb eigenes try/except, und die
            # Emission steht als letzte Anweisung, die ueberhaupt noch
            # scheitern koennte.
            if client is not None:
                try:
                    client.close()
                except Exception:                 # noqa: BLE001
                    logger.exception("closing the restart client failed")
            # Muss feuern: nur dieses Signal macht den Menuepunkt wieder
            # anklickbar.
            bridge.restart_finished.emit(outcome.ok, outcome.message)

    def _start_restart() -> None:
        restart_action.setEnabled(False)
        try:
            threading.Thread(target=_restart_worker, daemon=True).start()
        except Exception:
            # Der Worker existiert dann nicht und kann restart_finished nie
            # senden — ohne diesen Zweig bliebe der Menuepunkt fuer den Rest
            # der Sitzung grau, obwohl gar nichts laeuft.
            logger.exception("could not start the restart worker thread")
            restart_action.setEnabled(True)

    restart_action.triggered.connect(_start_restart)

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

    # Die Ursache eines Worker-Abbruchs, damit run_tray sie weiterreichen
    # kann. Der Worker legt sie ab, *bevor* er das Signal schickt; die
    # QueuedConnection ist die Synchronisation zwischen beiden Threads.
    worker_failure: list[BaseException] = []

    def _fatal(message: str) -> None:
        # Laeuft im GUI-Thread. Ohne diesen Weg stirbt der Worker still und
        # das Tray steht fuer immer auf grau, ohne dass jemand erfaehrt warum.
        logger.warning("tray worker stopped: %s", message)
        app.quit()

    bridge.fatal.connect(_fatal)

    async def _main() -> None:
        try:
            await notifier.connect()
        except NotifierUnavailable as exc:
            worker_failure.append(exc)
            bridge.fatal.emit(
                f"Keine Desktop-Benachrichtigungen verfügbar: {exc}"
            )
            return

        # Die Zuweisung steht mit *im* try, nicht davor. Sie kann scheitern:
        # ein umbenanntes LoopContext-Feld (TypeError), ein Fehler in
        # Watcher(session, state), ein AttributeError auf websockets.connect.
        # Draussen wuerde so ein Fehlschlag den Worker-Thread still beenden —
        # worker_failure bliebe leer, bridge.fatal feuerte nie, app.exec()
        # liefe weiter, das Icon bliebe fuer immer grau und der Prozess endete
        # spaeter mit 0, was systemd als sauberen Abschluss liest. Jede
        # Anweisung nach notifier.connect() braucht einen Zweig, der ablegt
        # *und* meldet.
        try:
            # Sichtbarkeit einmal beim Start bestimmen. Eine Rollenaenderung
            # braucht danach einen Neustart des Trays — das ist selten genug.
            account = await asyncio.to_thread(
                fetch_account_facts, session.client(), session.refresh_access
            )
            bridge.restart_visible.emit(
                menu_visible(account.is_admin, account.is_admin is not None)
            )

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
            await run_loop(ctx)
        except Exception as exc:
            # asyncio.run() in einem Thread wuerde den Traceback nach stderr
            # schreiben und den Thread beenden; das Icon bliebe grau ohne
            # Erklaerung. Der Weg nach draussen geht ueber das Signal.
            logger.exception("tray worker stopped unexpectedly")
            worker_failure.append(exc)
            bridge.fatal.emit(f"Tray-Hintergrund beendet: {exc}")

    threading.Thread(target=lambda: asyncio.run(_main()), daemon=True).start()
    code = app.exec()

    if worker_failure:
        # Weiterreichen statt hier in einen Exit-Code uebersetzen: was
        # "dauerhaft" und was "voruebergehend" heisst, entscheidet main.py.
        # Ohne dieses raise liefert app.exec() nach app.quit() eine 0, und
        # ein Tray, das sich beim Anmelden zu frueh gestartet hat, waere fuer
        # systemd sauber beendet — kein Neustart, leeres Panel.
        raise worker_failure[0]
    return code
