"""Die drei Listen der setzbaren Akustik-Knoten muessen deckungsgleich sein (#570).

Sie stehen bewusst dreimal: Backend-Erlaubnisliste, Pydantic-Schema und die
Frontend-Konstante, damit das Frontend seine Liste nicht vom Backend bezieht.
Was fehlte, war die Kopplung -- ein fuenfter Knoten (Kernel 6.13:
fan_zero_rpm_enable) verlangt drei Aenderungen, und wer eine vergisst, sieht
entweder keinen Regler oder einen still verworfenen PUT.
"""
import re
from pathlib import Path

from app.schemas.gpu_fan_acoustics import GpuFanAcousticsValues
from app.services.power.fan_gpu_acoustics import ACOUSTIC_NODES

TSX = (
    Path(__file__).resolve().parents[2]
    / "client" / "src" / "components" / "fan-control" / "FirmwareFanNotice.tsx"
)


def _frontend_nodes() -> list[str]:
    """SETTABLE_NODES aus der TSX-Datei lesen.

    Textlich statt ueber einen JS-Lauf: der Test soll in der Backend-Suite
    ohne node laufen. Findet der Ausdruck die Konstante nicht mehr, faellt
    das als leere Liste auf -- deshalb prueft der erste Test die Laenge.
    """
    block = re.search(r"const SETTABLE_NODES\s*=\s*\[(.*?)\]", TSX.read_text(encoding="utf-8"), re.S)
    if block is None:
        return []
    return re.findall(r"['\"]([a-z_]+)['\"]", block.group(1))


def test_die_frontend_liste_ist_ueberhaupt_auffindbar():
    """Schutz gegen einen vakuum-gruenen Test: findet der Ausdruck die
    Konstante nicht, waeren alle Vergleiche unten trivial erfuellt."""
    assert len(_frontend_nodes()) == len(ACOUSTIC_NODES)


def test_backend_erlaubnisliste_und_schema_stimmen_ueberein():
    assert set(ACOUSTIC_NODES) == set(GpuFanAcousticsValues.model_fields)


def test_frontend_liste_und_backend_erlaubnisliste_stimmen_ueberein():
    assert set(_frontend_nodes()) == set(ACOUSTIC_NODES)
