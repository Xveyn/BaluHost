"""Entscheidet, ob und worauf ein Luefter an die Board-Automatik zurueckgeht (#534).

Reine Regel ohne sysfs- und ohne DB-Zugriff. Der Entwurf steht und faellt mit
einem Grundsatz: zurueckgeschrieben wird ausschliesslich ein Wert, den BaluHost
am selben Chip selbst gelesen hat. Ein geratener Treibermodus waere eine
Annahme ueber fremde Hardware, die niemand ueberpruefen kann.
"""
from __future__ import annotations

from typing import Optional

# Ab hier regelt der Chip selbst. Darunter liegen die beiden Zustaende, in
# denen er es NICHT tut:
#   1 = Handsteuerung (jemand hat uebernommen -- in aller Regel wir)
#   0 = "no fan speed control (i.e. fan at full speed)" laut hwmon-Konvention;
#       der nct6775-Treiber setzt dabei zusaetzlich Duty 255
_LOWEST_AUTOMATIC_MODE = 2


def is_observation(value: Optional[int]) -> bool:
    """Taugt der gelesene pwm_enable-Wert als Rueckgabeziel?"""
    return value is not None and value >= _LOWEST_AUTOMATIC_MODE


def resolve_restore_value(scanned: Optional[int],
                          stored: Optional[int]) -> Optional[int]:
    """Der Rueckgabewert: juengere Beobachtung schlaegt gespeicherten Wert.

    Ist der gescannte Wert keine Beobachtung, bleibt der gespeicherte
    unveraendert -- er stammt dann aus einem frueheren Kaltstart und ist das
    Beste, was wir haben. Gibt es auch den nicht, gibt es keine Rueckgabe.

    Der gespeicherte Wert wird dabei ebenso gegen is_observation() geprueft
    wie der gescannte: die Spalte traegt keinen CHECK-Constraint, und die
    Zusage "nur beobachtete Werte" soll nicht davon abhaengen, wer sie einmal
    gefuellt hat (manuelle DB-Aenderung, ein kuenftiges Backfill, ein von Hand
    geflickter Dump).
    """
    if is_observation(scanned):
        return scanned
    return stored if is_observation(stored) else None


def needs_release(current: Optional[int], target: Optional[int]) -> bool:
    """Muss geschrieben werden?

    Ein nicht lesbarer Ist-Wert gilt als Abweichung: lieber einmal zu viel
    schreiben, als die Board-Automatik ausgeschaltet zu lassen.
    """
    if target is None:
        return False
    return current != target
