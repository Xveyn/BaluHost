"""Die Gesamtbewertung der RAID-Arrays fuer die Mountpoint-Anzeige (#570).

Vorgeschichte: die Bewertung startete auf "optimal" und wurde nur von
"degraded" oder "rebuilding" davon weggehoben -- jeder andere Wert galt damit
als in Ordnung. Solange get_status() bei einem unlesbaren Array die ganze
Antwort abbrach, fiel das nicht auf (der Endpunkt lieferte einen 500er:
falsch, aber laut). Seit dieselbe Runde die Antwort pro Array degradieren
laesst und "unknown" melden kann, waere daraus ein GRUENES Signal fuer einen
Fehlerfall geworden.
"""
import pytest

from app.api.routes.files import worst_array_status
from app.schemas.system import RaidArray


def _array(name: str, status: str) -> RaidArray:
    return RaidArray(name=name, level="raid1", size_bytes=1024,
                     status=status, devices=[])


def test_ohne_arrays_gilt_optimal():
    assert worst_array_status([]) == "optimal"


def test_alles_optimal_bleibt_optimal():
    assert worst_array_status([_array("md0", "optimal"), _array("md1", "optimal")]) == "optimal"


def test_ein_unlesbares_array_ist_nicht_optimal():
    """Der eigentliche Regressionstest: 'unknown' darf nicht als gesund
    durchgehen. Vorher meldete die Mountpoint-Anzeige hier 'optimal' und die
    Oberflaeche zeigte kein Warnzeichen."""
    assert worst_array_status([_array("md0", "optimal"), _array("md1", "unknown")]) == "unknown"


def test_ein_scrub_ist_kein_fehler():
    """'checking' entsteht bei Debians monatlichem checkarray. Das ist
    Wartung, kein Handlungsbedarf -- ein Warndreieck waere ein Fehlalarm."""
    assert worst_array_status([_array("md0", "checking")]) == "optimal"


@pytest.mark.parametrize("status", ["rebuilding", "inactive", "unknown"])
def test_jeder_nicht_gesunde_zustand_hebt_die_bewertung(status):
    assert worst_array_status([_array("md0", status)]) == status


def test_degraded_sticht_alles_andere():
    """Auch wenn es hinten steht und ein anderer Zustand schon gesetzt ist."""
    arrays = [_array("md0", "checking"), _array("md1", "unknown"), _array("md2", "degraded")]
    assert worst_array_status(arrays) == "degraded"


def test_degraded_sticht_auch_als_erstes():
    arrays = [_array("md0", "degraded"), _array("md1", "rebuilding")]
    assert worst_array_status(arrays) == "degraded"
