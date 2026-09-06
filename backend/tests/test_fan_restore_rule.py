"""Regel fuer die Rueckgabe an die Board-Automatik (#534).

Zurueckgeschrieben wird ausschliesslich ein Wert, den BaluHost am selben Chip
selbst gelesen hat. 0 und 1 sind keine Automatik: 1 ist Handsteuerung, 0 heisst
laut hwmon-Konvention "no fan speed control (i.e. fan at full speed)".
"""
import pytest

from app.services.power.fan_restore import (
    is_observation,
    needs_release,
    resolve_restore_value,
)


@pytest.mark.parametrize("value,expected", [
    (5, True),      # Smart Fan IV
    (2, True),      # Thermal Cruise
    (1, False),     # Handsteuerung -- jemand hat uebernommen
    (0, False),     # Vollgas, keine Chip-Regelung
    (None, False),  # nicht lesbar
])
def test_is_observation(value, expected):
    assert is_observation(value) is expected


def test_observation_is_stored():
    assert resolve_restore_value(scanned=5, stored=None) == 5


def test_newer_observation_wins():
    """Der Chip meldet jetzt Thermal Cruise -- das ist die aktuellere Wahrheit."""
    assert resolve_restore_value(scanned=2, stored=5) == 2


def test_non_observation_keeps_stored_value():
    """Nach einem Deploy-Neustart steht dort 1; der gespeicherte Wert bleibt."""
    assert resolve_restore_value(scanned=1, stored=5) == 5
    assert resolve_restore_value(scanned=0, stored=5) == 5
    assert resolve_restore_value(scanned=None, stored=5) == 5


def test_without_observation_there_is_no_target():
    """Der Kern des Entwurfs: ohne Beobachtung passiert nichts."""
    assert resolve_restore_value(scanned=1, stored=None) is None
    assert resolve_restore_value(scanned=0, stored=None) is None
    assert resolve_restore_value(scanned=None, stored=None) is None


def test_manual_control_value_in_storage_is_never_returned():
    """Die Spalte hat keinen CHECK-Constraint -- der gespeicherte Wert wird
    deshalb ebenso geprueft wie der gescannte. Eine "1" in der DB (manuelle
    Aenderung, Backfill, geflickter Dump) darf beim Beenden nicht als
    Rueckgabeziel dienen -- das waere genau der kaputte Zustand, den #534
    beseitigen soll.
    """
    assert resolve_restore_value(scanned=None, stored=1) is None


def test_full_speed_value_in_storage_is_never_returned():
    """Wie oben, fuer den anderen Nicht-Automatik-Wert (Vollgas, kein
    CHECK-Constraint auf der Spalte)."""
    assert resolve_restore_value(scanned=None, stored=0) is None


def test_needs_release_only_with_a_target():
    assert needs_release(current=1, target=5) is True
    assert needs_release(current=5, target=5) is False
    assert needs_release(current=1, target=None) is False


def test_manual_at_full_speed_reads_as_zero_and_still_needs_release():
    """reg_to_pwm_enable() meldet Manual mit Duty 255 als 0, nicht als 1."""
    assert needs_release(current=0, target=5) is True


def test_unreadable_current_value_is_treated_as_deviation():
    """Lieber einmal zu viel schreiben als die Automatik ausgeschaltet lassen."""
    assert needs_release(current=None, target=5) is True
