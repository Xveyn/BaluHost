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


def test_jedes_permission_skript_laeuft_ueber_den_helfer():
    """Kein direkter `sudo bash` mehr auf eines der drei Skripte.

    Der Helfer traegt die Vorabpruefung; ein Aufruf daran vorbei haette sie
    nicht. Geprueft wird deshalb die Abwesenheit des alten Musters, nicht nur
    die Anwesenheit des neuen."""
    text = _text()
    assert "run_permission_script()" in text, "der Helfer muss definiert sein"
    # Zeilenfortsetzungen aufloesen, sonst stuenden Aufruf und Pfad in
    # verschiedenen Zeilen und die Zuordnung waere nicht pruefbar. Die alte
    # Fassung fragte nur, ob BEIDE Zeichenketten irgendwo in der Datei stehen --
    # das haette auch ein Aufruf am Helfer vorbei erfuellt.
    verbunden = re.sub(r"\\\s*\n\s*", " ", text)
    aufrufe = re.findall(r'run_permission_script\s+"[^"]+"\s+(\S+)', verbunden)
    for skript in ("install-amd-gpu-permissions.sh", "install-hardware-sudoers.sh",
                   "install-power-sudoers.sh"):
        assert any(skript in a for a in aufrufe), f"{skript} laeuft nicht ueber den Helfer"
    # Der Helfer ist die einzige Stelle, die eines dieser Skripte ausfuehrt.
    assert text.count('sudo bash "$script"') == 1
    assert 'sudo bash "$POWER_SUDOERS_SCRIPT"' not in text
    assert 'sudo bash "$HARDWARE_SUDOERS_SCRIPT"' not in text
    assert 'sudo bash "$AMD_GPU_SCRIPT"' not in text


def test_der_helfer_prueft_vorher_ob_der_aufruf_erlaubt_waere():
    """`sudo -n -l` fragt, ob der Aufruf erlaubt WAERE, ohne ihn auszufuehren.
    Ohne diese Vorabpruefung landete die Ursache als 'a password is required'
    im Log und die Zusammenfassung sagte nur 'failed'."""
    text = _text()
    assert 'sudo -n -l bash "$script"' in text


def test_die_meldung_nennt_den_befehl_der_es_behebt():
    """Eine Warnung ohne Handlungsanweisung kostet beim naechsten Mal wieder
    eine Stunde Suche."""
    text = _text()
    assert "install-deploy-sudoers.sh" in text
    assert "NOT PERMITTED" in text


def test_die_handlungsanweisung_kann_den_naechsten_deploy_nicht_lahmlegen():
    """Zwei Fallen, beide in der Review gefunden, beide hier festgenagelt.

    `$USER` in der ausgegebenen Zeile: die Anweisung wird in einer root-Shell
    ausgefuehrt, dort waere das "root". Die Datei wuerde fuer root gerendert,
    der Dienstbenutzer verloere alle NOPASSWD-Rechte, und der naechste Deploy
    braeche beim Neustart der Dienste ab.

    Fehlendes `env`: sudo lehnt Zuweisungen in der Kommandozeile ohne SETENV
    ab (env_reset ist Debian-Standard) -- der Befehl waere schlicht nicht
    ausfuehrbar.
    """
    zeile = next(
        z for z in _text().splitlines()
        if "install-deploy-sudoers.sh" in z and "log_warn" in z
    )
    assert "$USER" not in zeile, "Benutzername muss beim Drucken eingesetzt werden"
    assert "$(id -un)" in zeile
    assert "sudo env BALUHOST_USER=" in zeile


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
    # Beide bash-Pfade, weil sudo den aufgeloesten Pfad vergleicht. Verankert
    # gegen den Doppelpunkt: "/bin/bash " ist eine Teilzeichenkette von
    # "/usr/bin/bash ", eine blosse Suche waere also schon durch die zweite
    # Zeile erfuellt und koennte den Verlust der ersten nicht bemerken.
    pfade = {re.search(r"NOPASSWD:\s+(\S+)", z).group(1) for z in treffer}
    assert pfade == {"/bin/bash", "/usr/bin/bash"}
