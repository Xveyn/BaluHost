"""Das Frontend erkennt einen Backend-503 nur am Text-Praefix wieder (#570).

FirmwareFanNotice.tsx prueft in isConfigUnavailable, ob `detail` mit
'GPU acoustics configuration' beginnt. Die beiden Meldungen entstehen in
fans.py an getrennten Stellen (Lesen bzw. Speichern der Konfiguration).
Aendert jemand eine der beiden ServiceUnavailableError-Meldungen, faellt die
Diagnose still auf die generische Fehlermeldung zurueck -- und ohne diesen
Test wuerde keine Suite rot.

Eigene Datei statt zweiter Testfunktion in test_gpu_acoustics_node_lists.py:
dort geht es um die Deckungsgleichheit dreier NAMEN-Listen, hier um einen
TEXT-Praefix zwischen zwei Dateien -- unterschiedliche Fundstellen, kein
gemeinsamer Kontext.
"""
import re
from pathlib import Path

TSX = (
    Path(__file__).resolve().parents[2]
    / "client" / "src" / "components" / "fan-control" / "FirmwareFanNotice.tsx"
)
FANS_ROUTE = Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "fans.py"


def _frontend_prefix() -> str | None:
    """Das im Frontend geprueften Praefix textlich aus der TSX lesen.

    Textlich statt ueber einen JS-Lauf: der Test soll in der Backend-Suite
    ohne node laufen (gleiches Muster wie test_gpu_acoustics_node_lists.py).
    """
    match = re.search(
        r"detail\.startsWith\(\s*['\"]([^'\"]+)['\"]\s*\)",
        TSX.read_text(encoding="utf-8"),
    )
    return match.group(1) if match else None


def _backend_messages() -> list[str]:
    """Die beiden ServiceUnavailableError-Meldungen aus fans.py lesen."""
    return re.findall(
        r'raise ServiceUnavailableError\(\s*"([^"]+)"\s*\)',
        FANS_ROUTE.read_text(encoding="utf-8"),
    )


def test_die_fundstellen_sind_ueberhaupt_auffindbar():
    """Schutz gegen einen vakuum-gruenen Test: findet einer der beiden
    Ausdruecke nichts, waeren die Vergleiche unten trivial erfuellt."""
    assert _frontend_prefix()
    assert len(_backend_messages()) == 2


def test_backend_meldungen_beginnen_mit_dem_vom_frontend_erkannten_praefix():
    prefix = _frontend_prefix()
    for message in _backend_messages():
        assert message.startswith(prefix)
