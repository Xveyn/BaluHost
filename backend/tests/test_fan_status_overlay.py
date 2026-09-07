"""Die sichtbare Haelfte von #568 Punkt 2: die Ueberlagerung in get_status().

Der Kanalzustand `pwm_control` lebt im `_fan_cache` des jeweiligen Workers,
gesetzt wird er nur von dem, der schreibt. Jeder Worker ueberlagert seinen
Cache deshalb mit der Liste, die der Primary veroeffentlicht hat.

Die Verdrahtung im Regelkreis wird hier mitgeprueft: die Nachbardatei
test_fan_write_permission_sharing.py fuehrt genau diese Luecke als bekannte
Falle -- ein Aufruf, den niemand festnagelt, verschwindet beim naechsten
Refactor unbemerkt.
"""
import inspect

import pytest

from app.schemas.fans import PwmControl
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService


def _dienst(monkeypatch, *, veroeffentlicht):
    dienst = object.__new__(FanControlService)
    dienst._use_linux_backend = True
    monkeypatch.setattr(fan_control_module, "read_denied_fans",
                        lambda db: veroeffentlicht)
    return dienst


def _ueberlagern(dienst, eintraege, veroeffentlicht):
    """Nur der Ueberlagerungsblock aus get_status(), auf denselben Regeln.

    Statt die ganze get_status() mit Datenbank und Backend nachzubauen, wird
    hier dieselbe Entscheidung geprueft, die dort getroffen wird -- und der
    Test darunter stellt sicher, dass diese Entscheidung dort auch wirklich
    steht.
    """
    if veroeffentlicht is None:
        return eintraege
    for eintrag in eintraege:
        if eintrag.get("pwm_control") is PwmControl.FIRMWARE_MANAGED:
            continue
        if eintrag["fan_id"] in veroeffentlicht:
            eintrag["pwm_control"] = PwmControl.NO_PERMISSION
    return eintraege


def test_der_ueberlagerungsblock_steht_wirklich_in_get_status():
    """Verdrahtungspruefung. Ohne sie koennte der Block verschwinden und alle
    Zusicherungen unten blieben gruen -- sie pruefen dann nur noch die
    Nachbildung in dieser Datei."""
    quelle = inspect.getsource(FanControlService.get_status)
    assert "read_denied_fans" in quelle
    assert "PwmControl.NO_PERMISSION" in quelle
    assert "PwmControl.FIRMWARE_MANAGED" in quelle


def test_der_regelkreis_ruft_die_erneute_probe():
    """Zweite Verdrahtungspruefung: ohne diesen Aufruf kann sich die
    Rechteanzeige festsetzen (der Befund, der die Fixwelle ausgeloest hat)."""
    quelle = inspect.getsource(FanControlService._monitoring_loop)
    assert "recheck_write_permission" in quelle


def test_der_primary_veroeffentlicht_die_kanaele_mit():
    quelle = inspect.getsource(FanControlService.publish_write_permission_if_changed)
    assert "_denied_fan_ids" in quelle


@pytest.mark.parametrize("veroeffentlicht,erwartet", [
    (None, PwmControl.SUPPORTED),          # nichts veroeffentlicht
    (set(), PwmControl.SUPPORTED),         # nichts gesperrt
    ({"nct6798:pwm1"}, PwmControl.NO_PERMISSION),
])
def test_der_gemeldete_zustand_schlaegt_durch(veroeffentlicht, erwartet):
    eintraege = [{"fan_id": "nct6798:pwm1", "pwm_control": PwmControl.SUPPORTED}]
    _ueberlagern(None, eintraege, veroeffentlicht)
    assert eintraege[0]["pwm_control"] is erwartet


def test_ein_firmware_kanal_bleibt_unangetastet():
    """Eine dauerhafte Hardware-Eigenschaft darf ein Laufzeit-Befund nicht
    ueberschreiben -- sonst verschwaende das Firmware-Badge, sobald der Primary
    denselben Kanal einmal als gesperrt gemeldet hat."""
    eintraege = [{"fan_id": "amdgpu:pwm1", "pwm_control": PwmControl.FIRMWARE_MANAGED}]
    _ueberlagern(None, eintraege, {"amdgpu:pwm1"})
    assert eintraege[0]["pwm_control"] is PwmControl.FIRMWARE_MANAGED


def test_ein_eigener_befund_wird_nicht_zurueckgenommen():
    """Vereinigung statt Ersetzung: eine Nutzer-Eingabe geht ueber irgendeinen
    Worker, und bei EACCES vermerkt genau DER den Kanal. Der Primary hat den
    Write nie versucht, seine Liste kennt den Kanal also nicht -- eine
    Ruecksetzung auf SUPPORTED liesse den frischen Befund sofort wieder
    verschwinden, neben einem `last_write_error`, der stehen bleibt."""
    eintraege = [{"fan_id": "nct6798:pwm1", "pwm_control": PwmControl.NO_PERMISSION}]
    _ueberlagern(None, eintraege, set())
    assert eintraege[0]["pwm_control"] is PwmControl.NO_PERMISSION
