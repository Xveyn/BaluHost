"""The entry point must fail politely, never with a traceback.

It runs from a systemd user unit, where a stack trace lands in the journal
and nowhere anybody looks.
"""

import ast
import dataclasses
import importlib
import pathlib
import tomllib
from unittest.mock import patch

from baluhost_tray import main as tray_main
from baluhost_tray.single_instance import AlreadyRunning


def test_second_instance_exits_cleanly(capsys):
    with patch("baluhost_tray.main.single_instance.acquire",
               side_effect=AlreadyRunning("held")):
        code = tray_main.run(argv=[])
    assert code == 0
    assert "läuft bereits" in capsys.readouterr().out


def test_missing_pairing_exits_zero_and_points_at_pair(capsys):
    """Exit 0, nicht 2: mit Restart=on-failure wuerde systemd sonst alle zehn
    Sekunden neu starten, bis die Unit auf failed steht."""
    with patch("baluhost_tray.main.single_instance.acquire"), \
         patch("baluhost_tray.main.tray_config.load_tokens", return_value=None):
        code = tray_main.run(argv=[])
    assert code == 0
    assert "--pair" in capsys.readouterr().out


def test_pairing_does_not_take_the_tray_lock():
    """--pair muss neben dem laufenden Dienst funktionieren."""
    names = []

    def _acquire(name="baluhost-tray"):
        names.append(name)
        return object()

    with patch("baluhost_tray.main.single_instance.acquire", side_effect=_acquire), \
         patch("baluhost_tray.main.run_pairing", return_value=0):
        tray_main.run(argv=["--pair"])

    assert names and all(n != "baluhost-tray" for n in names)


def test_no_session_bus_exits_with_hint(capsys):
    from baluhost_tray.notify import NotifierUnavailable

    with patch("baluhost_tray.main.single_instance.acquire"), \
         patch("baluhost_tray.main.tray_config.load_tokens", return_value=object()), \
         patch("baluhost_tray.main.start_qt_app",
               side_effect=NotifierUnavailable("no bus")):
        code = tray_main.run(argv=[])
    assert code == 3
    assert "Plasma" in capsys.readouterr().out


def test_pairing_runs_before_the_token_check():
    """Wer koppeln will, hat per Definition noch keine Token."""
    with patch("baluhost_tray.main.single_instance.acquire"), \
         patch("baluhost_tray.main.tray_config.load_tokens", return_value=None), \
         patch("baluhost_tray.main.run_pairing", return_value=0) as pair:
        code = tray_main.run(argv=["--pair"])
    assert code == 0
    assert pair.called


def test_web_url_is_not_the_api_port():
    """Zwei Adressen, nicht eine: die API liegt auf dem FastAPI-Port, die
    Web-UI hinter nginx. Wer :8000 im Browser oeffnet, sieht die API."""
    assert tray_main.DEFAULT_WEB_URL != tray_main.DEFAULT_BASE_URL
    assert ":8000" not in tray_main.DEFAULT_WEB_URL


def test_both_urls_reach_the_qt_layer():
    seen = {}

    def _start(base_url, web_url):
        seen["base"] = base_url
        seen["web"] = web_url
        return 0

    with patch("baluhost_tray.main.single_instance.acquire"), \
         patch("baluhost_tray.main.tray_config.load_tokens", return_value=object()), \
         patch("baluhost_tray.main.start_qt_app", side_effect=_start):
        code = tray_main.run(
            argv=["--base-url", "http://box:8000", "--web-url", "https://box"]
        )
    assert code == 0
    assert seen == {"base": "http://box:8000", "web": "https://box"}


def test_pairing_flow_needs_no_qt():
    """--pair darf PyQt6 nicht hereinziehen.

    Das Extra 'tray' ist auf einer Konsole womoeglich nie installiert worden;
    ein PyQt6-Import auf Modulebene wuerde `baluhost-tray --pair` dort mit
    ImportError beenden. Der Import hier ist die Probe.
    """
    import importlib
    import sys

    assert "PyQt6" not in sys.modules
    importlib.import_module("baluhost_tray.pairing_cli")
    assert "PyQt6" not in sys.modules


def _tray_module_ast() -> ast.Module:
    """tray.py als Syntaxbaum.

    Importieren geht hier nicht: PyQt6 ist in dieser Umgebung nicht
    installiert, und genau deshalb laeuft sonst *nichts* gegen tray.py. Der
    Baum ist die einzige Probe, die die Verdrahtung dort ueberhaupt pruefen
    kann, ohne einen halben Qt-Nachbau zu erfinden.
    """
    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "baluhost_tray" / "tray.py"
    ).read_text()
    return ast.parse(source)


def test_tray_builds_the_loop_context_with_fields_that_exist():
    """Ein umbenanntes LoopContext-Feld faellt sonst erst auf dem Zielrechner
    auf — und dort als TypeError im Worker-Thread."""
    from baluhost_tray.loop import LoopContext

    call = next(
        node for node in ast.walk(_tray_module_ast())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "LoopContext"
    )
    passed = {kw.arg for kw in call.keywords}
    fields = {f.name for f in dataclasses.fields(LoopContext)}
    required = {
        f.name for f in dataclasses.fields(LoopContext)
        if f.default is dataclasses.MISSING
        and f.default_factory is dataclasses.MISSING
    }
    assert not passed - fields, f"unbekannte Felder: {passed - fields}"
    assert not required - passed, f"fehlende Pflichtfelder: {required - passed}"


def test_tray_imports_names_that_exist():
    for node in _tray_module_ast().body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module or not node.module.startswith("baluhost_tray"):
            continue
        module = importlib.import_module(node.module)
        for alias in node.names:
            assert hasattr(module, alias.name), f"{node.module}.{alias.name} fehlt"


# Alles, was im asyncio-Thread laeuft: der Worker selbst und die Rueckrufe,
# die der Worker aufruft.
WORKER_FUNCTIONS = ("_main", "_sink", "_fatal_from_worker")
# Qt-Aufrufe, die den GUI-Thread brauchen.
FORBIDDEN_IN_WORKER = {"setIcon", "setToolTip", "show", "setChecked", "exec", "quit"}


def test_the_worker_never_touches_qt_directly():
    """Qt gehoert dem GUI-Thread.

    Der Worker meldet ueber pyqtSignal — thread-uebergreifend eine
    QueuedConnection und der einzig korrekte Weg. setIcon aus dem
    asyncio-Thread waere eine Regelverletzung mit offenem Ausgang.
    """
    tree = _tray_module_ast()
    workers = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in WORKER_FUNCTIONS
    ]
    assert {w.name for w in workers} >= {"_main", "_sink"}

    emits = 0
    for worker in workers:
        for node in ast.walk(worker):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            assert node.func.attr not in FORBIDDEN_IN_WORKER, (
                f"{worker.name} ruft {node.func.attr}() direkt im Worker-Thread"
            )
            if node.func.attr == "emit":
                emits += 1
    assert emits, "der Worker meldet gar nichts an den GUI-Thread"


def _pyproject() -> dict:
    root = pathlib.Path(__file__).resolve().parents[2]
    return tomllib.loads((root / "pyproject.toml").read_text())


def test_the_tray_package_is_collected_by_the_build():
    """Sonst waere das Konsolenskript installiert und das Modul nicht — die
    Unit begaenne mit ModuleNotFoundError."""
    find = _pyproject()["tool"]["setuptools"]["packages"]["find"]
    assert "baluhost_tray*" in find["include"]
    # Das vorhandene exclude muss beim Ergaenzen erhalten bleiben, sonst
    # landen die Tests im Wheel.
    assert "tests*" in find["exclude"]


def test_the_icons_ship_with_the_package():
    """Ohne package-data zeigt icon_path() im Wheel auf nichts."""
    package_data = _pyproject()["tool"]["setuptools"]["package-data"]
    assert "*.png" in package_data["baluhost_tray.icons"]


def test_the_console_script_and_the_extra_exist():
    data = _pyproject()["project"]
    assert data["scripts"]["baluhost-tray"] == "baluhost_tray.main:cli"
    extra = " ".join(data["optional-dependencies"]["tray"])
    assert "PyQt6" in extra
    assert "websockets" in extra
