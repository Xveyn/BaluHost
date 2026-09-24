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
