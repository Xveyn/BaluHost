"""Console pairing flow.

Separate from tray.py because that module imports PyQt6 at module level and
`--pair` has to work on a box where the tray extra was never installed.
"""

from __future__ import annotations

import time
from urllib.parse import urlsplit

from baluhost_tray import pairing
from baluhost_tray.config import save_tokens
from baluhost_tui.client import BackendClient

# Wohin die Web-UI zum Freigeben zeigt, wenn der Server keinen brauchbaren
# Pfad mitliefert. Ein Link auf die bekannte Standardseite ist besser als
# keiner — dort steht die Geraeteliste, der Rest erklaert sich selbst.
DEFAULT_APPROVAL_PATH = "/devices?pair=1"


def approval_link(verification_url: str, web_url: str) -> str:
    """Die Adresse, die ein Mensch abtippt — Web-UI, nicht API.

    Das Backend baut `verification_url` aus `request.base_url`
    (`services/desktop_pairing.py`). Das Tray fragt die API auf :8000, also
    steht dort der Backend-Port drin, und wer dem Link folgt, landet auf der
    API statt auf der Seite mit dem Eingabefeld.

    Pfad und Query bleiben vom Server: benennt die Web-UI die Route um, zieht
    das hier ohne Aenderung mit. Ersetzt wird nur der Ursprung, und den kennt
    das Tray aus `--web-url`.
    """
    base = web_url.rstrip("/")
    try:
        parts = urlsplit(verification_url)
    except ValueError:
        return f"{base}{DEFAULT_APPROVAL_PATH}"
    if not parts.path:
        return f"{base}{DEFAULT_APPROVAL_PATH}"
    return f"{base}{parts.path}" + (f"?{parts.query}" if parts.query else "")


def run_pairing_flow(base_url: str, web_url: str) -> int:
    """Print the code, poll until approved. Never a traceback.

    Zwei Adressen, mit Absicht: `base_url` ist die API, `web_url` die Web-UI
    hinter nginx. Sie faellt nur in der Entwicklung zusammen.
    """
    client = BackendClient(server=base_url)
    try:
        pending = pairing.start_pairing(client)
    except Exception as exc:
        print(f"Kopplung konnte nicht gestartet werden: {exc}")
        return 4

    print(f"Code: {pending.user_code}")
    print(f"Freigeben unter: {approval_link(pending.verification_url, web_url)}")

    warned = False
    deadline = time.monotonic() + pending.expires_in
    while time.monotonic() < deadline:
        try:
            tokens = pairing.poll_once(client, pending.device_code)
        except pairing.PairingDenied:
            print("Freigabe abgelehnt.")
            return 4
        except pairing.PairingExpired:
            print("Code abgelaufen oder ungültig — bitte erneut versuchen.")
            return 4
        except Exception as exc:
            # Netzwerkaussetzer oder unerwartete Antwort. Der Code laeuft
            # ohnehin ab, also weiter versuchen statt abbrechen — aber die
            # Meldung nur einmal, sonst steht sie hundertmal im Terminal.
            if not warned:
                print(f"Backend gerade nicht erreichbar ({exc}) — weiter versuchen …")
                warned = True
            tokens = None
        if tokens:
            save_tokens(tokens)
            print("Gekoppelt.")
            return 0
        time.sleep(pending.interval + 1)   # 12/min Limit, nicht auf der Kante

    print("Code abgelaufen — bitte erneut versuchen.")
    return 4
