"""Entry point for `baluhost-tray`.

Every failure here is a message, never a traceback: this runs from a systemd
user unit, where a stack trace lands in the journal and nowhere anybody looks.
"""

from __future__ import annotations

import argparse
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
        print("BaluHost Tray läuft bereits in dieser Sitzung.")
        return 0

    # Vor der Token-Pruefung: wer koppeln will, hat per Definition noch keine.
    if args.pair:
        return run_pairing(args.base_url)

    if tray_config.load_tokens() is None:
        # Exit 0 on purpose: with Restart=on-failure a non-zero code would
        # have systemd restart this every ten seconds until the unit fails.
        print("Nicht gekoppelt. Einmalig ausführen: baluhost-tray --pair")
        return 0

    try:
        return start_qt_app(args.base_url, args.web_url)
    except NotifierUnavailable as exc:
        print("Keine Desktop-Sitzung gefunden — das Tray braucht ein "
              f"laufendes Plasma mit D-Bus. ({exc})")
        return 3
    except ImportError as exc:
        # Das Extra 'tray' fehlt. Ohne diesen Zweig steht im Journal ein
        # Traceback ueber PyQt6, statt zu sagen, was zu tun ist.
        print("PyQt6 fehlt — installieren mit: pip install "
              f"'baluhost-backend[tray]' ({exc})")
        return 3


def cli() -> None:
    sys.exit(run())
