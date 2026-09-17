"""Kein Deploy-Skript raet mehr, wem die Box gehoert (#581).

Der Fork-Deploy reicht an die Box nur `github.actor` weiter -- ein Protokollfeld.
Wer der Linux-Dienstbenutzer ist, erfaehrt er nirgends. Zwei der vier
Permission-Skripte fielen deshalb auf `sven` zurueck, den Login des
Upstream-Maintainers:

    BALUHOST_USER="${BALUHOST_USER:-sven}"

Auf BaluNode ist dieser Name zufaellig richtig, upstream ist `deploy-fork.yml`
ohnehin tot -- betroffen war ausschliesslich der Fork-Selfhosting-Pfad aus #207.
Dort hiess es entweder `usermod -aG video sven` gegen einen nicht existierenden
Benutzer, oder -- schlimmer -- ein fuer `sven` gerendertes
`/etc/sudoers.d/baluhost-deploy`, das dem echten Deploy-Benutzer alle
NOPASSWD-Rechte nimmt. Beides endete als gruener Deploy mit einer non-fatal
WARN-Zeile.

Dazu kam die zweite Haelfte desselben Fehlers: die Skriptpfade waren an
`/opt/baluhost` genagelt, obwohl `deploy-fork.yml` ein abweichendes
`DEPLOY_FORK_INSTALL_DIR` anbietet.

Geprueft wird textlich -- die Skripte laufen nur auf der Maschine, aber jede
Ruecknahme der Aufloesung faellt hier auf. Muster wie in
test_ci_deploy_permission_sync.py (#570).
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "deploy" / "scripts"
TEMPLATES = REPO / "deploy" / "install" / "templates"
DEPLOY_SUDOERS = TEMPLATES / "baluhost-deploy-sudoers"
MODULE_10 = REPO / "deploy" / "install" / "modules" / "10-systemd-services.sh"
CI_DEPLOY = SCRIPTS / "ci-deploy.sh"

# Die vier Skripte, die die Deploy-sudoers-Vorlage als root freigibt, plus das
# Bootstrap-Skript, das diese Vorlage selbst rendert.
PERMISSION_SCRIPTS = (
    "install-amd-gpu-permissions.sh",
    "install-hardware-sudoers.sh",
    "install-power-sudoers.sh",
    "install-companion.sh",
    "install-deploy-sudoers.sh",
)

# Die beiden, die den Dienstbenutzer brauchen und ihn frueher geraten haben.
USER_RESOLVING_SCRIPTS = (
    "install-amd-gpu-permissions.sh",
    "install-deploy-sudoers.sh",
    # Die beiden Vorbilder -- mitgeprueft, damit das Muster nicht einseitig
    # wieder zerfaellt.
    "install-hardware-sudoers.sh",
    "install-power-sudoers.sh",
)


def _text(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def _anleitende_docs():
    """Doku, der ein Operator folgt -- ohne docs/superpowers/.

    Dort liegen Plaene und Specs: Aufzeichnungen dessen, was einmal war,
    einschliesslich der Fehler, die sie beheben. Ein Plan von 2026-05-02 zitiert
    `BALUHOST_USER=sven` genau deshalb, weil er den Rueckfall beschreibt.
    Historie umzuschreiben, damit ein Test gruen wird, waere die falsche
    Reihenfolge."""
    return [
        p for p in (REPO / "docs").rglob("*.md")
        if "superpowers" not in p.relative_to(REPO).parts
    ]


def test_die_geprueften_dateien_existieren_ueberhaupt():
    """Schutz gegen einen vakuum-gruenen Test: ohne Inhalt waeren alle
    Zusicherungen unten bedeutungslos."""
    for name in PERMISSION_SCRIPTS:
        assert (SCRIPTS / name).is_file(), f"{name} fehlt"
        assert _text(name).startswith("#!/bin/bash"), f"{name} ist kein Shell-Skript"
    assert DEPLOY_SUDOERS.is_file()
    assert MODULE_10.is_file()


def test_kein_permission_skript_raet_auf_einen_benutzernamen():
    """Der Kern von #581. Ein Rueckfall auf irgendeinen festen Login ist immer
    falsch: auf einer fremden Box existiert er nicht oder gehoert dem falschen
    Konto, und der Deploy meldet trotzdem Erfolg."""
    for name in PERMISSION_SCRIPTS:
        treffer = [
            z for z in _text(name).splitlines()
            if re.search(r"BALUHOST_USER\s*=\s*\"?\$\{BALUHOST_USER:-[^}]+\}", z)
            and not re.search(r"BALUHOST_USER:-\$\{SERVICE_USER:-\}", z)
        ]
        assert not treffer, f"{name} raet den Dienstbenutzer: {treffer}"
    # Namentlich, damit auch eine umgeschriebene Variante des Rueckfalls auffaellt.
    for name in PERMISSION_SCRIPTS:
        assert ":-sven}" not in _text(name), f"{name} faellt weiterhin auf 'sven' zurueck"


def test_die_benutzeraufloesung_folgt_ueberall_demselben_muster():
    """Explizit > `User=` des laufenden Dienstes > Abbruch. Abgeleitet aus
    install-hardware-sudoers.sh, das es seit jeher richtig macht."""
    for name in USER_RESOLVING_SCRIPTS:
        text = _text(name)
        assert 'systemctl show -p User --value' in text, \
            f"{name} liest den Dienstbenutzer nicht aus systemd"
        assert 'BALUHOST_USER="${BALUHOST_USER:-${SERVICE_USER:-}}"' in text, \
            f"{name} verwendet nicht die uebliche Override-Reihenfolge"


def test_eine_unbestimmbare_identitaet_bricht_ab_statt_zu_raten():
    """Ein Abbruch ist hier besser als ein Treffer auf den falschen Benutzer:
    `usermod -aG video <falsch>` und ein fuer den falschen Namen gerendertes
    sudoers sind beide schwerer zu bemerken als ein Fehlschlag."""
    for name in USER_RESOLVING_SCRIPTS:
        text = _text(name)
        block = text.split('BALUHOST_USER="${BALUHOST_USER:-${SERVICE_USER:-}}"', 1)[1]
        # Der Abbruch muss direkt folgen, nicht irgendwo spaeter in der Datei.
        kopf = block[:400]
        assert 'if [[ -z "$BALUHOST_USER" ]]; then' in kopf, \
            f"{name} prueft das Ergebnis der Aufloesung nicht"
        assert "exit 1" in kopf, f"{name} bricht bei unbestimmbarem Benutzer nicht ab"
        assert "BALUHOST_USER is unset" in kopf, \
            f"{name} nennt dem Operator nicht den Ausweg"


def test_kein_permission_skript_nagelt_seine_pfade_an_opt_baluhost():
    """Die zweite Haelfte von #581: `deploy-fork.yml` bietet ein abweichendes
    DEPLOY_FORK_INSTALL_DIR an. Ein hart verdrahtetes /opt/baluhost als Default
    laesst die Skripte dort an 'template not found' scheitern -- also genau
    wieder an einer WARN-Zeile, nur an einer anderen."""
    for name in PERMISSION_SCRIPTS:
        treffer = [
            z for z in _text(name).splitlines()
            if re.search(r"^\s*(TEMPLATE|INSTALL_DIR)=.*/opt/baluhost", z)
        ]
        assert not treffer, f"{name} hat weiterhin einen /opt/baluhost-Default: {treffer}"


def test_die_skripte_finden_ihre_vorlagen_ueber_den_eigenen_ort():
    """Wo das Skript liegt, liegt auch das Repo -- das ist die einzige Quelle,
    die auf jeder Box stimmt, ohne dass jemand sie durchreichen muss."""
    for name in ("install-deploy-sudoers.sh", "install-hardware-sudoers.sh",
                 "install-power-sudoers.sh", "install-companion.sh"):
        text = _text(name)
        assert 'BASH_SOURCE[0]' in text, \
            f"{name} leitet sein Install-Verzeichnis nicht aus dem eigenen Ort ab"


def test_die_deploy_sudoers_vorlage_templatet_das_install_verzeichnis():
    """@@INSTALL_DIR@@ ist keine Neuerfindung: baluhost-update-sudoers nutzt es
    bereits, gerendert vom selben process_template-Aufruf in Modul 10."""
    text = DEPLOY_SUDOERS.read_text(encoding="utf-8")
    regeln = [z for z in text.splitlines() if "NOPASSWD" in z and not z.lstrip().startswith("#")]
    assert regeln, "die Vorlage muss ueberhaupt Regeln enthalten"
    pfad_regeln = [z for z in regeln if "/deploy/scripts/" in z]
    assert pfad_regeln, "die Vorlage muss die Permission-Skripte freigeben"
    for z in pfad_regeln:
        assert "@@INSTALL_DIR@@/deploy/scripts/" in z, f"Pfad nicht getemplatet: {z}"
        assert "/opt/baluhost" not in z, f"Pfad weiterhin an /opt/baluhost genagelt: {z}"


def test_die_freigegebenen_pfade_bleiben_exakt_und_ohne_glob():
    """Gegenprobe zur Templatisierung: aus einem festen Pfad darf kein Muster
    werden. Genau ein Skript pro Zeile, kein Stern, kein ALL."""
    regeln = [
        z for z in DEPLOY_SUDOERS.read_text(encoding="utf-8").splitlines()
        if "NOPASSWD" in z and "/deploy/scripts/" in z and not z.lstrip().startswith("#")
    ]
    for z in regeln:
        befehl = z.split("NOPASSWD:", 1)[1].strip()
        interpreter, _, rest = befehl.partition(" ")
        assert interpreter in ("/bin/bash", "/usr/bin/bash"), f"fremder Interpreter: {z}"
        assert rest.endswith(".sh"), f"kein exakter Skriptpfad: {z}"
        assert "*" not in befehl, f"Glob in einer Root-Freigabe: {z}"
        assert "?" not in befehl, f"Glob in einer Root-Freigabe: {z}"


def test_modul_10_setzt_jeden_platzhalter_der_vorlage_ein():
    """Die Invariante, die den Fix zusammenhaelt: ein Platzhalter, den das
    Rendern nicht kennt, bliebe woertlich in der Live-sudoers-Datei stehen --
    genau der Fehler aus #126, nur an einer anderen Datei."""
    tokens = set(re.findall(r"@@([A-Z_]+)@@", DEPLOY_SUDOERS.read_text(encoding="utf-8")))
    assert tokens, "die Vorlage muss Platzhalter haben"

    modul = MODULE_10.read_text(encoding="utf-8")
    aufruf = re.search(
        r'process_template "\$DEPLOY_SUDOERS_TEMPLATE" "\$DEPLOY_SUDOERS_OUTPUT"(.*?)\n\s*chmod',
        modul, re.S,
    )
    assert aufruf, "der Rendering-Aufruf fuer die Deploy-sudoers ist nicht auffindbar"
    uebergeben = set(re.findall(r'"([A-Z_]+)=', aufruf.group(1)))
    assert tokens <= uebergeben, f"nicht eingesetzt: {sorted(tokens - uebergeben)}"


def test_das_bootstrap_skript_setzt_dieselben_platzhalter_ein():
    """install-deploy-sudoers.sh rendert dieselbe Vorlage auf einer bereits
    installierten Box. Kennt es einen Platzhalter nicht, landet er woertlich in
    /etc/sudoers.d/baluhost-deploy und die Regel greift nie."""
    tokens = set(re.findall(r"@@([A-Z_]+)@@", DEPLOY_SUDOERS.read_text(encoding="utf-8")))
    text = _text("install-deploy-sudoers.sh")
    for token in tokens:
        assert f"@@{token}@@" in text, f"install-deploy-sudoers.sh ersetzt @@{token}@@ nicht"


def test_keine_doku_weist_einen_operator_auf_einen_festen_login_an():
    """Der Fix im Code nuetzt nichts, solange die Anleitung den Rueckfall von
    Hand wiederherstellt. AMD_GPU_PERMISSIONS.{de,en}.md sagte woertlich
    `sudo BALUHOST_USER=sven bash ... install-deploy-sudoers.sh` -- wer dem
    folgte, rendert die Deploy-sudoers fuer den falschen Benutzer und nimmt dem
    echten Deploy-Benutzer jedes NOPASSWD-Recht."""
    treffer = []
    for pfad in _anleitende_docs():
        for nr, zeile in enumerate(pfad.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"BALUHOST_USER=(sven|baluhost)\b", zeile):
                treffer.append(f"{pfad.relative_to(REPO)}:{nr}: {zeile.strip()}")
    assert not treffer, "Doku schreibt einen festen Dienstbenutzer vor:\n" + "\n".join(treffer)


def test_jede_doku_zeile_mit_override_ist_ueberhaupt_ausfuehrbar():
    """`sudo VAR=wert cmd` lehnt sudo ohne SETENV ab (env_reset ist
    Debian-Standard) -- die Zeile waere schlicht nicht ausfuehrbar. Deshalb
    schreiben ci-deploy.sh und SELF_HOSTING.md `sudo env BALUHOST_USER=…`."""
    treffer = []
    for pfad in _anleitende_docs():
        for nr, zeile in enumerate(pfad.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"sudo\s+BALUHOST_USER=", zeile):
                treffer.append(f"{pfad.relative_to(REPO)}:{nr}: {zeile.strip()}")
    assert not treffer, "'sudo env' fehlt, die Zeile laeuft so nicht:\n" + "\n".join(treffer)


def test_das_gefaehrlichste_skript_sichert_die_alte_datei():
    """install-deploy-sudoers.sh ist die einzige der vier sudoers-Dateien, deren
    Fehlrender den Deploy-Benutzer komplett entrechtet -- und die einzige, die
    bisher keine Sicherung anlegte. Seine beiden Geschwister tun es seit jeher."""
    for name in ("install-deploy-sudoers.sh", "install-hardware-sudoers.sh",
                 "install-power-sudoers.sh"):
        text = _text(name)
        assert ".bak.$(date" in text, f"{name} legt keine Sicherung der Live-Datei an"


def test_das_install_verzeichnis_wird_normalisiert():
    """sudo vergleicht den Skriptpfad als Zeichenkette, nicht als Pfad. Ein
    INSTALL_DIR mit Schluss-Slash rendert `/opt/baluhost//deploy/...`, waehrend
    der zweite Renderer (cd+pwd) `/opt/baluhost/deploy/...` schreibt -- danach
    scheitert `sudo -n -l` und alle drei Syncs werden still uebersprungen.

    Eine Schleife, kein einzelnes %/: `/srv/x//` muss ebenfalls bei `/srv/x`
    landen. Und `/` darf nicht zur leeren Zeichenkette werden."""
    for pfad in (SCRIPTS / "ci-deploy.sh", REPO / "deploy" / "install" / "lib" / "config.sh"):
        text = pfad.read_text(encoding="utf-8")
        assert 'while [[ "${#INSTALL_DIR}" -gt 1 && "$INSTALL_DIR" == */ ]]; do' in text, \
            f"{pfad.name} normalisiert INSTALL_DIR nicht (Schleife + Guard)"
        assert 'INSTALL_DIR="${INSTALL_DIR%/}"' in text, \
            f"{pfad.name} entfernt den Schluss-Slash nicht"


def test_die_platzhalter_ersetzung_kennt_kein_sonderzeichen():
    """Gemessen auf bash 5.2.26 (Debian 13 liefert 5.2):

        $ T='X@@D@@Y'; R='/opt/balu&host'; echo "${T//@@D@@/$R}"
        X/opt/balu@@D@@hostY

    `patsub_replacement` ist seit 5.2 standardmaessig AN und gibt '&' im Ersatz
    dieselbe Bedeutung wie in sed: 'die ganze Fundstelle'. Der erste Anlauf
    dieses Fixes tauschte sed gegen Bash-Ersetzung und aenderte damit gar
    nichts. Ein Install-Pfad mit '&' rendert dann eine kaputte Regel, die visudo
    trotzdem akzeptiert -- sie installiert sich still und greift nie.

    Geprueft werden beide Renderer derselben Vorlage."""
    for text, wo in (
        (_text("install-deploy-sudoers.sh"), "install-deploy-sudoers.sh"),
        ((REPO / "deploy" / "install" / "lib" / "common.sh").read_text(encoding="utf-8"),
         "lib/common.sh (process_template)"),
    ):
        assert "shopt -u patsub_replacement" in text, \
            f"{wo} schaltet patsub_replacement nicht ab"

    skript = _text("install-deploy-sudoers.sh")
    assert not re.search(r"sed\s.*@@INSTALL_DIR@@", skript), \
        "INSTALL_DIR wird weiterhin per sed ersetzt"

    # Die Bibliothek wird gesourct -- sie darf die Einstellung des Aufrufers
    # nicht dauerhaft veraendern.
    lib = (REPO / "deploy" / "install" / "lib" / "common.sh").read_text(encoding="utf-8")
    assert "shopt -s patsub_replacement" in lib, \
        "process_template stellt patsub_replacement nicht wieder her"


def test_ci_deploy_behauptet_nicht_mehr_den_alten_rueckfall():
    """Der Kommentar im SYNC_PERMISSIONS-Block beschrieb den Rueckfall als
    beabsichtigt ('defaults BALUHOST_USER=sven internally'). Bliebe er stehen,
    wuerde der naechste Leser die Aufloesung fuer ueberfluessig halten."""
    text = CI_DEPLOY.read_text(encoding="utf-8")
    assert "BALUHOST_USER=sven" not in text
    assert "sven" not in text, "ci-deploy.sh nennt weiterhin einen konkreten Login"
