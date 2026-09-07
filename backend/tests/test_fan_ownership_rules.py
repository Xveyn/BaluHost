"""Die Regeln fuer die Rueckgabe an die Board-Automatik (#534 Punkt 1).

Reine Funktionen, deshalb hier ohne Hardware pruefbar. Jeder Test entspricht
einem der Befunde, an denen der erste Anlauf gescheitert ist -- sie stehen als
Prueflliste in #534.
"""
import pytest

from app.services.power.fan_ownership import (
    FanOwnership,
    is_released,
    ownership_after_release,
    should_release,
)


def _bedingungen(**abweichungen):
    basis = dict(
        at_write_cap=True,
        ownership=FanOwnership.OWNED,
        has_observed_restore_value=True,
        is_firmware_managed=False,
        is_active=True,
    )
    basis.update(abweichungen)
    return basis


def test_am_deckel_und_besessen_wird_freigegeben():
    assert should_release(**_bedingungen()) is True


def test_unterhalb_des_deckels_passiert_nichts():
    """Ein einzelner Fehlschlag ist kein Grund, die Regelung abzugeben --
    genau deshalb haengt die Bedingung am Deckel des Backoffs und nicht am
    ersten Fehler."""
    assert should_release(**_bedingungen(at_write_cap=False)) is False


@pytest.mark.parametrize("zustand", [FanOwnership.RELEASED, FanOwnership.ABANDONED])
def test_ein_bereits_freigegebener_kanal_wird_nicht_erneut_freigegeben(zustand):
    """Die Bedingung ist ein ZUSTAND, keine Flanke. Waere sie als 'erstmals am
    Deckel' formuliert, feuerte sie pro Prozess hoechstens einmal: das Backoff
    wird nur von einem erfolgreichen Write geleert, nach einer
    Wiederuebernahme ohne Erfolg steht der Zaehler also schon am Deckel."""
    assert should_release(**_bedingungen(ownership=zustand)) is False


def test_ohne_beobachteten_wert_wird_nichts_zurueckgegeben():
    """Die geerbte Randbedingung aus #556: zurueckgegeben wird nur ein Wert,
    den BaluHost am selben Chip selbst gelesen hat. Ein geratener
    Treibermodus waere eine Annahme ueber fremde Hardware -- ein falsch
    geratener Wert stellte den Luefter still ab.

    Auf BaluNode betrifft das pwm7: dort gibt es nichts zurueckzugeben, und
    der Kanal bleibt in Handsteuerung."""
    assert should_release(**_bedingungen(has_observed_restore_value=False)) is False


def test_ein_firmware_kanal_wird_nicht_freigegeben():
    """BaluHost hat ihn nie uebernommen (#480) -- es gibt nichts abzugeben,
    und ein Write gegen den Knoten waere genau der, den #480 abgeschafft hat."""
    assert should_release(**_bedingungen(is_firmware_managed=True)) is False


def test_ein_inaktiver_luefter_wird_nicht_freigegeben():
    assert should_release(**_bedingungen(is_active=False)) is False


def test_eine_geglueckte_rueckgabe_heisst_das_board_regelt():
    assert ownership_after_release(True) is FanOwnership.RELEASED


def test_eine_gescheiterte_rueckgabe_heisst_niemand_regelt():
    """release_to_board() schreibt UND liest zurueck; ein False heisst also
    nicht nur 'Schreibfehler', sondern auch 'der Wert liegt danach nicht an'.
    Beides fuehrt zum selben Ergebnis -- und eine Oberflaeche, die hier 'das
    Board regelt' anzeigt, waere unehrlich."""
    assert ownership_after_release(False) is FanOwnership.ABANDONED


@pytest.mark.parametrize("zustand,erwartet", [
    (FanOwnership.OWNED, False),
    (FanOwnership.RELEASED, True),
    (FanOwnership.ABANDONED, True),
])
def test_der_regelkreis_laesst_beide_freigabe_zustaende_in_ruhe(zustand, erwartet):
    """Auch bei ABANDONED: dort regelt zwar niemand, aber weiterzuschreiben
    braechte nichts ausser Lograuschen -- der Kanal hat gerade acht
    Fehlschlaege in Folge geliefert."""
    assert is_released(zustand) is erwartet
