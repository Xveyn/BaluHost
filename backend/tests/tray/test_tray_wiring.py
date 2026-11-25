"""Rauchtest für die Qt-Verdrahtung.

Läuft nur, wo das Extra [tray] installiert ist — im venv dieses Repos ist
PyQt6 nicht dabei, im Produktions-venv und im System-Python schon:

    QT_QPA_PLATFORM=offscreen python3 -m pytest tests/tray/test_tray_wiring.py \
        -o addopts="" -p no:cacheprovider

Ohne diesen Test importiert **kein** Test `tray.py`, und ein Namensfehler auf
Funktionsebene fällt erst auf BaluNode auf.
"""
import os

import pytest

pytest.importorskip("PyQt6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _qt_teardown_order():
    """Erst die Widgets einsammeln, dann die QApplication freigeben.

    run_tray() legt ein QApplication als lokale Variable an; Menues, Bridge
    und Lambdas bilden mit ihm Referenzzyklen und ueberleben den Aufruf.
    Raeumte erst pytests gc_collect_harder() beim Beenden auf, zerstoerte
    der GC in beliebiger Reihenfolge — QMenu nach seiner QApplication —
    und der Lauf endete mit Segfault (Exit 139), obwohl alle Tests gruen
    waren. Solange `app` hier festgehalten wird, ist sie kein Muell; der
    erste collect() raeumt nur den Rest ab.
    """
    yield
    import gc

    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    gc.collect()
    del app
    gc.collect()


class _NoThread:
    """Der Worker-Thread wird nicht gestartet — kein Bus, kein Netzwerk."""

    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass


def test_run_tray_builds_the_menu(monkeypatch):
    """Läuft run_tray bis zum Ende durch, ohne dass ein Name kollidiert.

    Genau hier wäre `queue = PopupQueue()` gegen ein `import queue` gelaufen:
    ein AttributeError zur Laufzeit, den weder ast.parse noch ein Modulimport
    findet.
    """
    from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

    from baluhost_tray import tray as tray_module

    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True)
    )
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    monkeypatch.setattr(tray_module.threading, "Thread", _NoThread)

    assert tray_module.run_tray("http://localhost:8000", "http://localhost") == 0


def test_restart_menu_label_exists():
    from baluhost_tray import tray as tray_module

    assert tray_module.MENU_RESTART.startswith("BaluHost neu starten")


def test_dialog_titles_differ_by_role():
    """Ein Titel fuer alle vier Dialoge las sich wie eine Aussage ueber den Ausgang.

    "BaluHost neu starten" ueber einer Meldung, die einen Fehlschlag meldet,
    widerspricht sich — bei der Abnahme genau so aufgefallen.
    """
    from baluhost_tray import tray as tray_module

    titles = {
        tray_module.TITLE_ASK,
        tray_module.TITLE_PROMPT,
        tray_module.TITLE_DONE,
        tray_module.TITLE_FAILED,
    }
    assert len(titles) == 4
    assert tray_module.TITLE_DONE != tray_module.TITLE_FAILED


def test_open_menu_and_left_click_share_one_guarded_handler():
    """Menue und Linksklick laufen ueber denselben Handler (SingleFlight)."""
    import inspect

    from baluhost_tray import tray as tray_module

    source = inspect.getsource(tray_module.run_tray)
    assert "_open_web" in source
    assert source.count("_open_web") >= 3          # def + Menue + Linksklick
    assert "SingleFlight" in source
    assert "open_url" in source


def _build_menu(monkeypatch):
    """run_tray ohne Worker; liefert die Bridge und das Untermenue."""
    from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

    from baluhost_tray import tray as tray_module

    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True)
    )
    captured = {}

    def _exec(self):
        for widget in QApplication.allWidgets():
            if isinstance(widget, QMenu) and widget.title() == "Always Awake":
                captured["menu"] = widget
        return 0

    monkeypatch.setattr(QApplication, "exec", _exec)
    monkeypatch.setattr(tray_module.threading, "Thread", _NoThread)
    monkeypatch.setattr(
        tray_module._Bridge,
        "__init__",
        (lambda orig: lambda self: (orig(self), captured.__setitem__("bridge", self))[0])(
            tray_module._Bridge.__init__
        ),
    )
    tray_module.run_tray("http://localhost:8000", "http://localhost")
    return captured


def test_awake_submenu_visibility_follows_admin(monkeypatch):
    captured = _build_menu(monkeypatch)
    menu, bridge = captured["menu"], captured["bridge"]
    action = menu.menuAction()

    assert action.isVisible() is False          # Start: Rolle unbekannt
    bridge.awake_visible.emit(True)
    assert action.isVisible() is True
    bridge.awake_visible.emit(False)            # None/False -> verborgen
    assert action.isVisible() is False


def _visible(menu):
    return [a for a in menu.actions() if a.isVisible() and not a.isSeparator()]


def test_awake_state_sets_check_and_title(monkeypatch):
    from datetime import datetime, timezone

    from baluhost_tray.awake import AwakeState

    captured = _build_menu(monkeypatch)
    menu, bridge = captured["menu"], captured["bridge"]

    bridge.awake_state.emit(AwakeState(True, None))
    checked = [a.text() for a in menu.actions() if a.isChecked()]
    assert checked == ["Dauerhaft"]
    assert [a.text() for a in _visible(menu)] == ["Aus", "1 Stunde", "8 Stunden", "Dauerhaft"]

    until = datetime(2026, 11, 25, 13, 0, tzinfo=timezone.utc)
    bridge.awake_state.emit(AwakeState(True, until))
    assert menu.title().startswith("Always Awake — bis ")

    bridge.awake_state.emit(AwakeState(False, None))
    assert [a.text() for a in menu.actions() if a.isChecked()] == ["Aus"]
    assert menu.title() == "Always Awake"
    assert not any(a.text().startswith("Bis ") for a in _visible(menu))


def test_awake_custom_deadline_is_shown_but_not_settable(monkeypatch):
    """Frist aus der Web-UI, die keinem Eintrag entspricht: angezeigt und
    angehakt, aber nicht anklickbar; die vier Eintraege bleiben waehlbar."""
    from datetime import datetime, timedelta, timezone

    from baluhost_tray.awake import AwakeState

    captured = _build_menu(monkeypatch)
    menu, bridge = captured["menu"], captured["bridge"]

    until = datetime.now(timezone.utc) + timedelta(hours=3, minutes=17)
    bridge.awake_state.emit(AwakeState(True, until))

    label = f"Bis {until.astimezone():%H:%M}"
    visible = _visible(menu)
    assert [a.text() for a in visible] == [label, "Aus", "1 Stunde", "8 Stunden", "Dauerhaft"]
    deadline = visible[0]
    assert deadline.isChecked() and not deadline.isEnabled()
    assert [a.text() for a in menu.actions() if a.isChecked()] == [label]
    assert all(a.isEnabled() for a in visible[1:])


def test_awake_shows_running_core_window(monkeypatch):
    from datetime import datetime, timedelta

    from baluhost_tray.awake import AwakeState

    captured = _build_menu(monkeypatch)
    menu, bridge = captured["menu"], captured["bridge"]

    ends = datetime.now() + timedelta(hours=2)
    bridge.awake_state.emit(
        AwakeState(False, None, core_active=True, core_label="Büro", core_until=ends)
    )
    core = [a for a in _visible(menu) if a.text().startswith("Kernzeit")]
    assert [a.text() for a in core] == [f"Kernzeit „Büro“ bis {ends:%H:%M}"]
    assert not core[0].isEnabled()
    assert menu.title() == f"Always Awake — Kernzeit bis {ends:%H:%M}"
    assert [a.text() for a in menu.actions() if a.isChecked()] == ["Aus"]

    bridge.awake_state.emit(AwakeState(False, None))
    assert not any(a.text().startswith("Kernzeit") for a in _visible(menu))
    assert all(not a.isVisible() for a in menu.actions() if a.isSeparator())


@pytest.mark.parametrize("title", ["BaluHost öffnen", "BaluHost neu starten"])
def test_secret_dialog_is_wide_enough_for_its_title(title):
    """Der statische getText()-Dialog war schmaler als sein Titel; KWin
    kuerzte ihn zu "BaluH...ffnen"."""
    from PyQt6.QtWidgets import QApplication, QLineEdit

    from baluhost_tray import tray as tray_module

    app = QApplication.instance() or QApplication([])  # noqa: F841
    dialog = tray_module._secret_dialog(title, "PIN für BaluHost:")
    try:
        assert dialog.windowTitle() == title
        assert dialog.textEchoMode() == QLineEdit.EchoMode.Password
        # Die tatsaechliche Breite nach dem Layout, nicht minimumWidth():
        # QInputDialog setzt die Mindestgroesse des Dialogs selbst zurueck.
        dialog.adjustSize()
        needed = dialog.fontMetrics().horizontalAdvance(title)
        assert dialog.width() >= needed + tray_module.TITLEBAR_RESERVE
        assert dialog.width() >= tray_module.MIN_DIALOG_WIDTH
    finally:
        dialog.deleteLater()
