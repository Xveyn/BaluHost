"""Entry point for `baluhost-tray`.

Every failure here is a message, never a traceback: this runs from a systemd
user unit, where a stack trace lands in the journal and nowhere anybody looks.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from baluhost_tray import config as tray_config
from baluhost_tray import single_instance
from baluhost_tray.notify import NotifierUnavailable

DEFAULT_BASE_URL = "http://localhost:8000"
# Die API liegt auf dem FastAPI-Port, die Web-UI hinter nginx. Wer :8000 im
# Browser oeffnet, sieht die API. Deshalb zwei getrennte Adressen.
DEFAULT_WEB_URL = "https://baluhost.local"
TRAY_LOCK = "baluhost-tray"
PAIR_LOCK = "baluhost-tray-pair"

# Zwei Klassen von Fehlschlag, zwei Exit-Codes — der Unterschied ist, ob ein
# Neustart helfen *kann*:
#
#   EXIT_DONE (0)      dauerhaft. Fehlende Kopplung behebt kein Neustart, das
#                      braucht einen Menschen. Mit Restart=on-failure wuerde
#                      ein Code ungleich null das alle zehn Sekunden
#                      wiederholen, bis die Unit auf failed steht.
#   EXIT_TRANSIENT (3) moeglicherweise voruebergehend. Beim Anmelden kann das
#                      Tray vor Plasma oder vor dem Session-Bus dran sein;
#                      dann hilft ein Neustart wirklich. Ist es doch
#                      dauerhaft, beendet das Startlimit der Unit die
#                      Versuche von selbst.
EXIT_DONE = 0
EXIT_TRANSIENT = 3

# Die Pakete des Extras 'tray'. Nur ein ImportError ueber diese ist "das Extra
# fehlt"; alles andere ist ein durchgereichter Fehler und damit unbekannter
# Ursache. Verglichen wird das oberste Paket, damit auch ein halb
# installiertes PyQt6 ("PyQt6.QtWidgets") noch als fehlendes Extra zaehlt.
TRAY_EXTRA_PACKAGES = {"PyQt6", "websockets"}

LOG_LEVEL_ENV = "BALUHOST_TRAY_LOG_LEVEL"


def start_qt_app(base_url: str, web_url: str) -> int:
    """Import Qt lazily so --pair and the tests work without PyQt6."""
    from baluhost_tray.tray import run_tray

    return run_tray(base_url, web_url)


def run_pairing(base_url: str) -> int:
    # Aus pairing_cli, nicht aus tray: tray.py importiert PyQt6 auf
    # Modulebene, und --pair soll ohne das Extra 'tray' funktionieren.
    from baluhost_tray.pairing_cli import run_pairing_flow

    return run_pairing_flow(base_url)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="baluhost-tray")
    parser.add_argument("--pair", action="store_true",
                        help="Dieses Gerät mit BaluHost koppeln")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help="API-Adresse des Backends")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL,
                        help="Adresse der Web-UI für Menü und Icon-Klick")
    args = parser.parse_args(argv)

    # Pairing takes its own lock so it works while the service is running.
    lock_name = PAIR_LOCK if args.pair else TRAY_LOCK
    try:
        single_instance.acquire(lock_name)
    except single_instance.AlreadyRunning:
        # Dauerhaft, solange die erste Instanz laeuft — und die tut ja genau
        # das Richtige. Nichts neu zu starten. Zwei Locks, zwei Meldungen: beim
        # PAIR_LOCK laeuft kein Tray, sondern eine zweite Kopplung, und wer
        # dann zum Dienst geschickt wird, sucht an der falschen Stelle.
        if args.pair:
            print("Es läuft bereits eine Kopplung — diese zuerst abschließen "
                  "oder abbrechen.")
        else:
            print("BaluHost Tray läuft bereits in dieser Sitzung.")
        return EXIT_DONE

    # Vor der Token-Pruefung: wer koppeln will, hat per Definition noch keine.
    if args.pair:
        return run_pairing(args.base_url)

    if tray_config.load_tokens() is None:
        # Der dauerhafte Fall: ohne Kopplung gibt es nichts zu zeigen, und
        # kein Neustart aendert daran etwas. Deshalb 0, siehe oben.
        print("Nicht gekoppelt. Einmalig ausführen: baluhost-tray --pair")
        return EXIT_DONE

    try:
        return start_qt_app(args.base_url, args.web_url)
    except NotifierUnavailable as exc:
        # Kein Session-Bus oder kein SNI-Host. Beim Anmelden kann das schlicht
        # zu frueh sein, also der voruebergehende Code — ein Neustart hat hier
        # eine echte Chance.
        print("Keine Desktop-Sitzung gefunden — das Tray braucht ein "
              f"laufendes Plasma mit D-Bus. ({exc})")
        return EXIT_TRANSIENT
    except ImportError as exc:
        # Nur das fehlende Extra 'tray' gehoert hierher. Ohne diesen Zweig
        # stuende im Journal ein Traceback ueber PyQt6, statt zu sagen, was zu
        # tun ist. Dauerhaft — ein Paket installiert sich nicht durch Warten.
        #
        # Die Einengung ist keine Kosmetik: der Zweig steht vor dem
        # Auffang-Zweig und griffe sonst auch fuer ImportErrors, die der
        # Worker durchgereicht hat. Der Nutzer laese dann "PyQt6 fehlt",
        # waehrend PyQt6 laengst da ist, und bekaeme EXIT_DONE — kein
        # Neustart, obwohl durchgereichte Worker-Fehler EXIT_TRANSIENT
        # verlangen. `name` kann None sein; dann ist es nicht das Extra.
        top_level = (exc.name or "").split(".")[0]
        if top_level in TRAY_EXTRA_PACKAGES:
            print(f"{top_level} fehlt — installieren mit: pip install "
                  f"'baluhost-backend[tray]' ({exc})")
            return EXIT_DONE
        return _report_unexpected(exc)
    except Exception as exc:
        return _report_unexpected(exc)


def _report_unexpected(exc: BaseException) -> int:
    """Der Auffang-Fall: alles, was der Worker durchgereicht hat.

    Unbekannte Ursache heisst: koennte voruebergehend sein, also darf systemd
    es noch einmal versuchen. Der Traceback steht ueber logger.exception in
    tray.py bereits im Journal; hier nur die Zeile, die ein Mensch liest.
    """
    print(f"Das Tray hat sich unerwartet beendet: {type(exc).__name__}: {exc}")
    return EXIT_TRANSIENT


def _setup_logging() -> None:
    """Wurzel-Logger einrichten — nur aus cli().

    Ohne basicConfig erreichen logger.warning/exception das Journal nur ueber
    logging.lastResort (stderr ab WARNING), und saemtliche logger.info/debug
    aus loop.py fallen ersatzlos weg — genau die Diagnose, die man nach einem
    Vorfall sucht. Das Journal liest stderr, deshalb dorthin.

    Nicht beim Import und nicht in run(): den Wurzel-Logger einzurichten ist
    das Vorrecht des Programms, dem der Prozess gehoert. Aus run() heraus
    faerbte es jeden Testlauf und jede Einbettung ein.
    """
    name = os.environ.get(LOG_LEVEL_ENV, "INFO").upper()
    level = getattr(logging, name, None)
    # Ein Tippfehler in der Unit-Umgebung darf den Start nicht kosten — und
    # getattr trifft auch Nicht-Level wie BASIC_FORMAT, daher die Typpruefung.
    if not isinstance(level, int):
        level = logging.INFO
    logging.basicConfig(
        level=level,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )


def cli() -> None:
    _setup_logging()
    sys.exit(run())
