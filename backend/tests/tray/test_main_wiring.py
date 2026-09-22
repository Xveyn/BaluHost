"""The entry point must fail politely, never with a traceback.

It runs from a systemd user unit, where a stack trace lands in the journal
and nowhere anybody looks.
"""

import ast
import dataclasses
import importlib
import logging
import pathlib
import sys
import tomllib
from unittest.mock import patch

import pytest

from baluhost_tray import main as tray_main
from baluhost_tray.single_instance import AlreadyRunning


def test_second_instance_exits_cleanly(capsys):
    """Ohne --pair ist der belegte Lock wirklich ein zweites Tray."""
    with patch("baluhost_tray.main.single_instance.acquire",
               side_effect=AlreadyRunning("held")):
        code = tray_main.run(argv=[])
    assert code == 0
    out = capsys.readouterr().out
    assert "läuft bereits" in out
    assert "Tray" in out


def test_a_second_pairing_is_not_reported_as_a_running_tray(capsys):
    """Beim PAIR_LOCK laeuft kein Tray, sondern eine zweite Kopplung.

    Die Meldung "BaluHost Tray laeuft bereits" schickt den Nutzer sonst zum
    Dienst, waehrend das, was ihm im Weg steht, sein eigenes zweites
    `baluhost-tray --pair` in einem anderen Terminal ist.
    """
    with patch("baluhost_tray.main.single_instance.acquire",
               side_effect=AlreadyRunning("held")):
        code = tray_main.run(argv=["--pair"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Kopplung" in out
    assert "Tray läuft bereits" not in out


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
    assert code == tray_main.EXIT_TRANSIENT
    assert code != 0, "sonst startet systemd nach einem zu fruehen Start nicht neu"
    assert "Plasma" in capsys.readouterr().out


def test_unexpected_worker_failure_is_treated_as_transient(capsys):
    """Unbekannte Ursache heisst: koennte voruebergehend sein.

    run_tray reicht den Fehler des Workers durch, statt app.exec() mit 0
    enden zu lassen — sonst waere ein Tray, das sich beim Anmelden zu frueh
    gestartet hat, fuer systemd sauber beendet.
    """
    with patch("baluhost_tray.main.single_instance.acquire"), \
         patch("baluhost_tray.main.tray_config.load_tokens", return_value=object()), \
         patch("baluhost_tray.main.start_qt_app",
               side_effect=RuntimeError("bus went away")):
        code = tray_main.run(argv=[])
    assert code == tray_main.EXIT_TRANSIENT
    out = capsys.readouterr().out
    assert "RuntimeError" in out and "bus went away" in out


def test_a_missing_extra_is_permanent_not_transient(capsys):
    """PyQt6 installiert sich nicht durch Warten — kein Neustart-Karussell."""
    with patch("baluhost_tray.main.single_instance.acquire"), \
         patch("baluhost_tray.main.tray_config.load_tokens", return_value=object()), \
         patch("baluhost_tray.main.start_qt_app",
               side_effect=ModuleNotFoundError(
                   "No module named 'PyQt6'", name="PyQt6")):
        code = tray_main.run(argv=[])
    assert code == tray_main.EXIT_DONE
    assert "pip install" in capsys.readouterr().out


def test_an_importerror_from_the_worker_is_transient_not_a_missing_extra(capsys):
    """Nicht jeder ImportError ist das fehlende Extra.

    Der Worker reicht durch, was ihn umgebracht hat. Kommt dabei ein
    ImportError heraus — ein Tippfehler in einem spaeten Import, ein
    kaputtes Fremdpaket —, waere "PyQt6 fehlt" die falsche Auskunft und
    EXIT_DONE der falsche Code: Zusage 6 verlangt fuer durchgereichte
    Worker-Fehler EXIT_TRANSIENT, damit systemd es noch einmal versuchen darf.
    """
    with patch("baluhost_tray.main.single_instance.acquire"), \
         patch("baluhost_tray.main.tray_config.load_tokens", return_value=object()), \
         patch("baluhost_tray.main.start_qt_app",
               side_effect=ImportError(
                   "cannot import name 'foo' from 'irgendwas'",
                   name="irgendwas")):
        code = tray_main.run(argv=[])
    assert code == tray_main.EXIT_TRANSIENT
    out = capsys.readouterr().out
    assert "PyQt6" not in out, "falsche Ursache genannt"
    assert "ImportError" in out


def test_an_importerror_without_a_name_is_not_mistaken_for_the_extra(capsys):
    """ImportError.name darf None sein — dann ist es nicht das Extra."""
    with patch("baluhost_tray.main.single_instance.acquire"), \
         patch("baluhost_tray.main.tray_config.load_tokens", return_value=object()), \
         patch("baluhost_tray.main.start_qt_app",
               side_effect=ImportError("irgendwas ging schief")):
        code = tray_main.run(argv=[])
    assert code == tray_main.EXIT_TRANSIENT


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


def test_the_entry_point_sets_up_logging(monkeypatch):
    """Ohne basicConfig erreicht nur logging.lastResort das Journal.

    Das ist stderr ab WARNING — saemtliche logger.info/debug aus loop.py
    fallen ersatzlos weg, also genau die Diagnose, die man nach einem Vorfall
    sucht. Das Journal liest stderr, deshalb dorthin.
    """
    monkeypatch.delenv(tray_main.LOG_LEVEL_ENV, raising=False)
    with patch("baluhost_tray.main.run", return_value=0), \
         patch("baluhost_tray.main.logging.basicConfig") as basic, \
         pytest.raises(SystemExit):
        tray_main.cli()

    assert basic.called, "cli() richtet kein Logging ein"
    assert basic.call_args.kwargs["level"] == logging.INFO
    assert basic.call_args.kwargs["stream"] is sys.stderr


def test_the_library_layer_does_not_configure_logging():
    """Nur cli() richtet ein.

    basicConfig beim Import oder in run() faerbt jede Einbettung und jeden
    Testlauf ein — das Wurzel-Logger-Setup gehoert dem Programm, das den
    Prozess besitzt, und das ist hier das Konsolenskript.
    """
    with patch("baluhost_tray.main.single_instance.acquire"), \
         patch("baluhost_tray.main.tray_config.load_tokens", return_value=object()), \
         patch("baluhost_tray.main.start_qt_app", return_value=0), \
         patch("baluhost_tray.main.logging.basicConfig") as basic:
        tray_main.run(argv=[])

    assert not basic.called, "run() fasst den Wurzel-Logger an"


def test_the_log_level_is_overridable(monkeypatch):
    monkeypatch.setenv(tray_main.LOG_LEVEL_ENV, "debug")
    with patch("baluhost_tray.main.run", return_value=0), \
         patch("baluhost_tray.main.logging.basicConfig") as basic, \
         pytest.raises(SystemExit):
        tray_main.cli()

    assert basic.call_args.kwargs["level"] == logging.DEBUG


def test_an_unknown_log_level_does_not_prevent_the_start(monkeypatch):
    """Ein Tippfehler in der Unit-Umgebung darf das Tray nicht kosten."""
    monkeypatch.setenv(tray_main.LOG_LEVEL_ENV, "geschwätzig")
    with patch("baluhost_tray.main.run", return_value=0), \
         patch("baluhost_tray.main.logging.basicConfig") as basic, \
         pytest.raises(SystemExit) as exit_info:
        tray_main.cli()

    assert exit_info.value.code == 0
    assert basic.call_args.kwargs["level"] == logging.INFO


def test_pairing_flow_needs_no_qt():
    """--pair darf PyQt6 nicht hereinziehen.

    Das Extra 'tray' ist auf einer Konsole womoeglich nie installiert worden;
    ein PyQt6-Import auf Modulebene wuerde `baluhost-tray --pair` dort mit
    ImportError beenden. Der Import hier ist die Probe.
    """
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
# die er aufruft. `_fatal` steht bewusst nicht hier — es haengt am Signal und
# laeuft damit im GUI-Thread.
WORKER_FUNCTIONS = ("_main", "_sink")
# Qt-Aufrufe, die den GUI-Thread brauchen. Nicht nur die, die heute im
# Modul vorkommen: der Waechter soll auch den Griff abfangen, den erst der
# naechste Umbau einfuehrt. Alles hier ist ueber die Objekte erreichbar, die
# im Closure von run_tray stehen — tray_icon, menu, quiet_action, app.
FORBIDDEN_IN_WORKER = {
    "setIcon", "setToolTip", "show", "setChecked", "exec", "quit",
    "hide", "setVisible", "processEvents", "showMessage", "setContextMenu",
}


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
            if not isinstance(node, ast.Call):
                continue
            # Der Waechter haengt an Namen. getattr(tray_icon, "setIcon")()
            # traegt keinen — der Name steht in einer Zeichenkette, und der
            # Aufruf ginge lautlos durch. Im Worker gibt es keinen ehrlichen
            # Grund dafuer, also faellt der Zugriff als Ganzes weg.
            if isinstance(node.func, ast.Name) and node.func.id == "getattr":
                raise AssertionError(
                    f"{worker.name}, Zeile {node.lineno}: getattr() im Worker "
                    "umgeht die Namenspruefung"
                )
            if not isinstance(node.func, ast.Attribute):
                continue
            assert node.func.attr not in FORBIDDEN_IN_WORKER, (
                f"{worker.name} ruft {node.func.attr}() direkt im Worker-Thread"
            )
            if node.func.attr == "emit":
                emits += 1
    assert emits, "der Worker meldet gar nichts an den GUI-Thread"


def _dotted(node) -> str | None:
    """'bridge.fatal.emit' fuer einen Attribute-Knoten, sonst None.

    Der Empfaenger ist die Zusage, nicht der Attributname: irgendein .append
    auf irgendeiner Liste und irgendein .emit auf irgendeinem Signal erfuellen
    die Kette nicht.
    """
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _calls(scope, dotted_name: str) -> list[ast.Call]:
    """Alle Aufrufe von <dotted_name>(...) in scope, in Quelltextreihenfolge."""
    found = [
        node for node in ast.walk(scope)
        if isinstance(node, ast.Call) and _dotted(node.func) == dotted_name
    ]
    return sorted(found, key=_pos)


def _pos(node) -> tuple[int, int]:
    return (node.lineno, node.col_offset)


def _is_docstring(stmt) -> bool:
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
        and isinstance(stmt.value.value, str)


def test_every_worker_failure_survives_the_thread_boundary():
    """Der Grund darf nicht im Worker-Thread bleiben.

    Ohne diese Kette endet der Prozess nach app.quit() mit 0, und systemd
    sieht einen sauberen Abschluss statt eines Fehlschlags. Laufen kann das
    hier niemand — PyQt6 fehlt —, also prueft der Syntaxbaum die Kette:
    der ganze Rumpf des Workers ist abgedeckt, jeder Fehlerzweig legt die
    Ursache ab *und* meldet sie — in dieser Reihenfolge —, und run_tray wirft
    die abgelegte Ursache nach app.exec() weiter.
    """
    tree = _tray_module_ast()
    worker = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_main"
    )

    # Abdeckung. Die vorige Fassung prueft nur die *vorhandenen* Fehlerzweige
    # und sieht deshalb nicht, was gar keinen hat: eine nackte Anweisung im
    # Rumpf beendet den Worker-Thread still — worker_failure bleibt leer,
    # bridge.fatal feuert nie, app.exec() laeuft weiter, das Icon bleibt grau
    # und der Prozess endet spaeter mit 0. Nur ein Docstring darf draussen
    # stehen; er kann nicht scheitern.
    for stmt in worker.body:
        assert isinstance(stmt, ast.Try) or _is_docstring(stmt), (
            f"_main, Zeile {stmt.lineno}: {type(stmt).__name__} steht ausserhalb "
            "jedes try — ein Fehlschlag dort erreicht den GUI-Thread nie"
        )

    handlers = [n for n in ast.walk(worker) if isinstance(n, ast.ExceptHandler)]
    assert handlers, "_main faengt gar nichts ab"
    for handler in handlers:
        appends = _calls(handler, "worker_failure.append")
        emits = _calls(handler, "bridge.fatal.emit")
        assert appends, (
            f"Fehlerzweig in Zeile {handler.lineno} legt die Ursache nicht in "
            "worker_failure ab"
        )
        assert emits, (
            f"Fehlerzweig in Zeile {handler.lineno} meldet dem GUI-Thread "
            "nichts ueber bridge.fatal"
        )
        # Reihenfolge: der Kommentar in tray.py traegt die Zusage "erst
        # ablegen, dann melden". Andersherum kann der GUI-Thread den Handler
        # abarbeiten, bevor die Ursache liegt — und run_tray findet nichts.
        assert _pos(appends[0]) < _pos(emits[0]), (
            f"Fehlerzweig in Zeile {handler.lineno} meldet, bevor er ablegt"
        )

    run_fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "run_tray"
    )
    exec_calls = _calls(run_fn, "app.exec")
    assert exec_calls, "run_tray ruft app.exec() gar nicht"

    reraises = [
        node for node in ast.walk(run_fn)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Subscript)
    ]
    assert reraises, "run_tray reicht die abgelegte Ursache nicht weiter"

    # Verankern, sonst passt der Zweig auf jedes `raise irgendwas[0]`: das
    # Weiterreichen muss hinter app.exec() stehen (davor liefe es nie) und
    # unter `if worker_failure:` (ohne die Wache wirft der Normalfall
    # IndexError statt den Exit-Code zurueckzugeben).
    guards = [
        node for node in ast.walk(run_fn)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name) and node.test.id == "worker_failure"
    ]
    guarded = {id(n) for g in guards for n in ast.walk(g)}
    for reraise in reraises:
        assert id(reraise) in guarded, (
            f"raise in Zeile {reraise.lineno} haengt an keinem "
            "'if worker_failure:'"
        )
        assert _pos(reraise) > _pos(exec_calls[-1]), (
            f"raise in Zeile {reraise.lineno} steht vor app.exec()"
        )


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
