"""Der Deploy benennt den einen sudoers-Blindfleck, statt still zu scheitern (#570).

Gemessen im Deploy-Log vom 2026-09-07 (Lauf 34142444452):

    INFO  Re-applying power sudoers...
    sudo: Ein Passwort ist notwendig
    WARN  Power sudoers sync failed (non-fatal - deploy continues).

`/etc/sudoers.d/baluhost-deploy` ist die einzige der vier sudoers-Dateien, die
ci-deploy.sh nicht neu rendern kann -- sie enthaelt genau die Erlaubnis, mit
der die anderen drei installiert werden. Neue Zeilen der Vorlage erreichen eine
bereits installierte Box deshalb nie, und der Fehlschlag sah aus wie ein
beliebiger Fehler statt wie eine fehlende Provisionierung.

Geprueft wird das Skript textlich: es laeuft nur auf der Maschine, aber die
Zusicherungen unten wuerden jede Ruecknahme der Diagnose bemerken.
"""
import re
from pathlib import Path

CI_DEPLOY = Path(__file__).resolve().parents[2] / "deploy" / "scripts" / "ci-deploy.sh"
DEPLOY_SUDOERS = (
    Path(__file__).resolve().parents[2]
    / "deploy" / "install" / "templates" / "baluhost-deploy-sudoers"
)


def _text() -> str:
    return CI_DEPLOY.read_text(encoding="utf-8")


def test_das_deploy_skript_ist_ueberhaupt_lesbar():
    """Schutz gegen einen vakuum-gruenen Test: ohne Inhalt waeren die
    Zusicherungen unten bedeutungslos."""
    assert CI_DEPLOY.is_file()
    assert "SYNC_PERMISSIONS" in _text()


def test_der_power_sudoers_aufruf_wird_vorher_auf_erlaubnis_geprueft():
    """`sudo -n -l` fragt, ob der Aufruf erlaubt WAERE, ohne ihn auszufuehren.
    Ohne diese Vorabpruefung landete die Ursache als 'a password is required'
    im Log und die Zusammenfassung sagte nur 'failed'."""
    text = _text()
    assert 'sudo -n -l bash "$POWER_SUDOERS_SCRIPT"' in text


def test_die_meldung_nennt_den_befehl_der_es_behebt():
    """Eine Warnung ohne Handlungsanweisung kostet beim naechsten Mal wieder
    eine Stunde Suche."""
    text = _text()
    assert "install-deploy-sudoers.sh" in text
    assert "NOT PERMITTED" in text


def test_die_vorlage_erlaubt_den_power_aufruf_ueberhaupt():
    """Die Gegenprobe zur Diagnose: waere der Eintrag in der Vorlage gar nicht
    vorhanden, waere nicht die Box veraltet, sondern das Repo falsch -- und die
    Handlungsanweisung ginge ins Leere."""
    zeilen = [
        z for z in DEPLOY_SUDOERS.read_text(encoding="utf-8").splitlines()
        if not z.lstrip().startswith("#")
    ]
    treffer = [z for z in zeilen if "install-power-sudoers.sh" in z]
    assert treffer, "die Vorlage muss den Aufruf erlauben"
    assert all("NOPASSWD" in z for z in treffer)
    # Beide bash-Pfade, weil sudo den aufgeloesten Pfad vergleicht.
    assert any(re.search(r"/bin/bash ", z) for z in treffer)
    assert any(re.search(r"/usr/bin/bash ", z) for z in treffer)
