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


# --- Die beiden Entscheidungen am echten Backend (#534) ----------------------
#
# Gegen die ECHTE LinuxFanControlBackend-Instanz, nicht gegen eine Attrappe:
# beide Zusagen unten waren in der ersten Fassung durch keinen Test gedeckt,
# und beide sind sicherheitsrelevant -- die eine entscheidet, wann ein Luefter
# abgegeben wird, die andere verhindert, dass acht erfolglose Nutzer-Klicks
# das ausloesen.

from unittest.mock import MagicMock  # noqa: E402

from app.services.power.fan_backend_linux import (  # noqa: E402
    PWM_BACKOFF_BASE_SECONDS,
    PWM_BACKOFF_MAX_SECONDS,
    LinuxFanControlBackend,
)


def _linux_backend(tmp_path):
    backend = object.__new__(LinuxFanControlBackend)
    backend._write_backoff = {}
    backend._monotonic = lambda: 0.0
    backend._has_write_permission = True
    pwm = tmp_path / "pwm1"
    pwm.write_text("128\n")
    backend._fan_cache = {
        "nct6798:pwm1": {
            "pwm_path": pwm,
            "pwm_enable_path": None,
            "device_driver": "nct6798",
            "pwm_control": None,
        }
    }
    return backend


def test_der_deckel_wird_nach_acht_fehlschlaegen_gemeldet(tmp_path):
    """Die Zahl steht nirgends geschrieben, sie folgt aus der Backoff-Formel:
    10 s * 2^(n-1) >= 900 s ist ab n = 8 erfuellt. Der Test rechnet sie aus
    denselben Konstanten nach, statt eine 8 zu behaupten -- aendert jemand die
    Formel, aendert sich beides gemeinsam."""
    backend = _linux_backend(tmp_path)
    erwartet = 1
    while PWM_BACKOFF_BASE_SECONDS * (2 ** (erwartet - 1)) < PWM_BACKOFF_MAX_SECONDS:
        erwartet += 1

    for n in range(1, erwartet + 1):
        backend._write_backoff["nct6798:pwm1"] = (n, 0.0)
        anzahl, am_deckel = backend.write_failure_state("nct6798:pwm1")
        assert anzahl == n
        assert am_deckel is (n >= erwartet), f"n={n}"


def test_ohne_fehlschlaege_ist_der_zaehler_leer(tmp_path):
    backend = _linux_backend(tmp_path)
    assert backend.write_failure_state("nct6798:pwm1") == (0, False)
    assert backend.write_failure_state("gibt-es-nicht") == (0, False)


@pytest.mark.asyncio
async def test_ein_erzwungener_fehlschlag_zaehlt_nicht(tmp_path, monkeypatch):
    """Der Befund aus #534: der Zaehler stieg unabhaengig von `force`. Acht
    erfolglose Nutzer-Klicks haetten den Luefter an die Board-Automatik
    abgegeben -- und wegen des fehlenden Rueckwegs waere der Nutzer nicht mehr
    zurueckgekommen."""
    backend = _linux_backend(tmp_path)

    async def _scheitert(path, value):
        return False, 13  # EACCES

    monkeypatch.setattr(backend, "_write_hwmon_file", _scheitert, raising=False)

    for _ in range(10):
        await backend.set_pwm("nct6798:pwm1", 50, force=True)

    assert backend.write_failure_state("nct6798:pwm1") == (0, False)


@pytest.mark.asyncio
async def test_ein_fehlschlag_aus_dem_regelkreis_zaehlt(tmp_path, monkeypatch):
    """Die Gegenrichtung -- sonst koennte der Zaehler nie den Deckel
    erreichen und die Rueckgabe nie ausloesen."""
    backend = _linux_backend(tmp_path)

    async def _scheitert(path, value):
        return False, 13

    monkeypatch.setattr(backend, "_write_hwmon_file", _scheitert, raising=False)

    await backend.set_pwm("nct6798:pwm1", 50)

    assert backend.write_failure_state("nct6798:pwm1")[0] == 1


def test_die_wiederuebernahme_raeumt_den_zaehler(tmp_path):
    backend = _linux_backend(tmp_path)
    backend._write_backoff["nct6798:pwm1"] = (8, 999.0)

    backend.clear_write_failures("nct6798:pwm1")

    assert backend.write_failure_state("nct6798:pwm1") == (0, False)
