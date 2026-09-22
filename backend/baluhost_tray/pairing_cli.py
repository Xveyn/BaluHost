"""Console pairing flow.

Separate from tray.py because that module imports PyQt6 at module level and
`--pair` has to work on a box where the tray extra was never installed.
"""

from __future__ import annotations

import time

from baluhost_tray import pairing
from baluhost_tray.config import save_tokens
from baluhost_tui.client import BackendClient


def run_pairing_flow(base_url: str) -> int:
    """Print the code, poll until approved. Never a traceback."""
    client = BackendClient(server=base_url)
    try:
        pending = pairing.start_pairing(client)
    except Exception as exc:
        print(f"Kopplung konnte nicht gestartet werden: {exc}")
        return 4

    print(f"Code: {pending.user_code}")
    print(f"Freigeben unter: {pending.verification_url}")
    print("Hinweis: zeigt der Link auf den Backend-Port, stattdessen die "
          "normale Web-UI öffnen und dort unter Geräte freigeben.")

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
