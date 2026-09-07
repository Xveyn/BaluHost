"""Die mdadm-/smartctl-Regeln decken genau die Aufrufformen des Codes ab (#570).

Bis #570 stand in der Vorlage `NOPASSWD: /sbin/mdadm` ohne Argumente. Ein
sudoers-Eintrag ohne Argumente erlaubt JEDE Argumentliste -- darunter
`mdadm --monitor --program <beliebiges Programm>`, also Codeausfuehrung als
root. Das war ein laengerer Hebel als das in derselben Runde behobene
`tee /sys/class/hwmon/*`.

Modellierung wie in test_hardware_sudoers_scope.py: sudo fuegt die Argumente zu
EINER Zeichenkette zusammen und matcht sie mit fnmatch ohne FNM_PATHNAME gegen
das Muster aus der Vorlage. Deshalb wird hier `binary + " " + " ".join(args)`
gegen den ganzen Eintrag gehalten.

Die Geraeteformen stammen aus einer Messung auf BaluNode (2026-09-07):
`smartctl --scan` meldet /dev/sda..sdc und /dev/nvme0..1, `/proc/mdstat` zeigt
md1 mit sda1 (Partition) und sdb (ganze Platte).
"""
import fnmatch
import re
from pathlib import Path

import pytest

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "deploy" / "install" / "templates" / "baluhost-hardware-sudoers"
)

MDADM = "/usr/sbin/mdadm"
SMARTCTL = "/usr/sbin/smartctl"


def _entries(binary: str) -> list[str]:
    """Alle sudoers-Eintraege fuer ein Binary, Zeilenfortsetzungen aufgeloest.

    Kommentarzeilen fallen vorher heraus -- sonst haette ein auskommentierter
    Eintrag die Erlaubnis-Tests gruen gelassen, waehrend die Funktion auf der
    Maschine ausfaellt.
    """
    zeilen = [
        z for z in TEMPLATE.read_text(encoding="utf-8").splitlines()
        if not z.lstrip().startswith("#")
    ]
    text = re.sub(r"\\\s*\n\s*", " ", "\n".join(zeilen))
    return [e.strip() for e in re.findall(rf"({re.escape(binary)}[^,\n]*)", text)]


def _erlaubt(binary: str, *args: str) -> bool:
    """Wie sudo entscheiden wuerde.

    Der Sonderfall ist der wichtige: ein Eintrag OHNE Argumente erlaubt in
    sudoers JEDE Argumentliste. Wer ihn wie ein argumentloses Kommando
    behandelt, baut sich einen Test, der den alten Zustand fuer sicher haelt --
    beim Nachstellen des alten Eintrags blieben die Ablehnungs-Tests hier
    zunaechst gruen.
    """
    kommando = " ".join([binary, *args])
    for eintrag in _entries(binary):
        if eintrag == binary:
            return True
        if fnmatch.fnmatchcase(kommando, eintrag):
            return True
    return False


def test_die_vorlage_traegt_ueberhaupt_eintraege():
    """Schutz gegen einen vakuum-gruenen Test: ohne gefundene Eintraege waeren
    alle Ablehnungs-Zusicherungen unten trivial erfuellt.

    Exakte Zahlen statt einer unteren Schranke, damit auch der Verlust
    einzelner Eintraege auffaellt. Zusammensetzung mdadm: 1 (--detail --scan)
    + 3*3 (--detail/--wait/--stop je Array-Form) + 4 (--zero-superblock je
    Geraeteform) + 5*12 (fuenf Verben x Array x Geraet) + 6 (--grow --bitmap
    je Array und Option) = 80, dazu 12 fuer --create (3 Array-Formen x 2
    Level-Laengen x mit/ohne --spare-devices) = 92.
    smartctl: 1 (--scan -j) + 2*2*4 (Selftest mit und ohne -A, je Typlaenge
    und Geraeteform) + 2*4 (-t short/long je Geraeteform) = 25.
    """
    assert len(_entries(MDADM)) == 92
    assert len(_entries(SMARTCTL)) == 25


def test_kein_eintrag_steht_ohne_argumente():
    """Der eigentliche Befund: ein Eintrag, der nur aus dem Binary besteht,
    erlaubt in sudoers JEDE Argumentliste -- genau der alte Zustand."""
    assert MDADM not in _entries(MDADM)
    assert SMARTCTL not in _entries(SMARTCTL)


# --- Die Aufrufformen aus services/hardware/raid/mdadm_backend.py ------------

@pytest.mark.parametrize("args", [
    ("--detail", "--scan"),                                   # :384
    ("--detail", "/dev/md1"),                                 # :180
    ("--detail", "/dev/md127"),
    ("--wait", "/dev/md1"),                                   # :108
    ("--stop", "/dev/md1"),                                   # :640
    ("--zero-superblock", "/dev/sdb"),                        # :651
    ("--zero-superblock", "/dev/sda1"),
    ("--zero-superblock", "/dev/nvme0n1"),
    ("/dev/md1", "--fail", "/dev/sdb"),                       # :82
    ("/dev/md1", "--remove", "/dev/sdb"),                     # :101, :139
    ("/dev/md1", "--add", "/dev/sda1"),                       # :102, :134
    ("/dev/md1", "--readwrite", "/dev/sdb"),                  # :145
    ("/dev/md1", "--write-mostly", "/dev/sdb"),               # :148
    ("/dev/md127", "--add", "/dev/nvme1n1p2"),
    ("/dev/md1", "--grow", "--bitmap=internal"),              # :129
    ("/dev/md1", "--grow", "--bitmap=none"),
])
def test_die_mdadm_aufrufe_des_codes_bleiben_erlaubt(args):
    assert _erlaubt(MDADM, *args)


def test_das_anlegen_eines_arrays_bleibt_erlaubt():
    """create_array baut die Argumentliste in dieser Reihenfolge (:605-624);
    die Zahl der Geraete ist variabel, deshalb ist dies die einzige Zeile mit
    einem '*' am Ende."""
    assert _erlaubt(MDADM, "--create", "/dev/md0", "--level=1",
                    "--raid-devices=2", "/dev/sda", "/dev/sdb")
    assert _erlaubt(MDADM, "--create", "/dev/md0", "--level=5",
                    "--raid-devices=3", "/dev/sda", "/dev/sdb", "/dev/sdc",
                    "--assume-clean")


# --- Die Aufrufformen aus services/hardware/smart/ ---------------------------

@pytest.mark.parametrize("args", [
    ("--scan", "-j"),                                                    # collector.py:40
    ("-t", "short", "/dev/sda"),                                         # scheduler.py:76
    ("-t", "long", "/dev/nvme0"),
])
def test_die_smartctl_aufrufe_des_codes_bleiben_erlaubt(args):
    assert _erlaubt(SMARTCTL, *args)


@pytest.mark.parametrize("dev_type,device", [
    ("sat", "/dev/sda"),
    ("scsi", "/dev/sdb"),
    ("scsi", "/dev/sdc"),
    ("auto", "/dev/sda1"),
    ("nvme", "/dev/nvme0"),
    ("nvme", "/dev/nvme1"),
    ("auto", "/dev/nvme0n1"),
])
def test_die_selftest_abfrage_wird_aus_dem_code_gewonnen(dev_type, device, monkeypatch):
    """Die Argumentliste stammt aus _run_smartctl, nicht aus dieser Datei.

    Der Grund ist ein konkreter Fehlschlag: eine frueherere Fassung dieses
    Tests hat die Form von Hand abgeschrieben und dabei uebersehen, dass
    utils.py fuer alles ohne 'nvme' ein '-A' an Position 3 EINSCHIEBT. Die
    sudoers-Vorlage kannte daraufhin nur die Form ohne -A -- auf der
    Referenzmaschine waeren genau die drei SATA-Platten still aus der
    SMART-Anzeige gefallen. Wer die Argumente abschreibt, testet seine eigene
    Lesart des Codes, nicht den Code.
    """
    from app.services.hardware.smart import utils

    aufgezeichnet: list[list[str]] = []

    class _Ergebnis:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def _aufzeichnen(argv, **_kwargs):
        aufgezeichnet.append(list(argv))
        return _Ergebnis()

    monkeypatch.setattr("subprocess.run", _aufzeichnen)
    utils._run_smartctl("/usr/sbin/smartctl", dev_type, device)

    assert len(aufgezeichnet) == 1
    argv = aufgezeichnet[0]
    assert argv[:2] == ["sudo", "-n"]
    assert _erlaubt(SMARTCTL, *argv[3:]), f"nicht abgedeckt: {' '.join(argv[2:])}"


# --- Was nicht mehr gehen darf ----------------------------------------------

@pytest.mark.parametrize("args", [
    # Der Ausfuehrungspfad: mdadm startet das Programm als root.
    ("--monitor", "--program", "/tmp/beliebig.sh"),
    ("--monitor", "--scan", "--program", "/tmp/beliebig.sh"),
    # Andere Modi, die der Code nie benutzt.
    ("--assemble", "--scan"),
    ("--manage", "/dev/md1", "--fail", "/dev/sdb"),
    ("--misc", "--zero-superblock", "/dev/sdb"),
    ("--grow", "/dev/md1", "--size=max"),
    # Ausbruch aus /dev.
    ("--detail", "/dev/../etc/shadow"),
    ("--zero-superblock", "/dev/../../etc/shadow"),
    # Ein Array-Argument, das keines ist.
    ("--stop", "/dev/sda"),
    ("/etc/shadow", "--fail", "/dev/sdb"),
])
def test_gefaehrliche_mdadm_formen_werden_abgelehnt(args):
    assert not _erlaubt(MDADM, *args)


@pytest.mark.parametrize("args", [
    # smartctl kann Geraeteeinstellungen dauerhaft veraendern.
    ("--set=security-freeze", "/dev/sda"),
    ("-t", "select,0-max", "/dev/sda"),
    # Ausbruch aus /dev.
    ("-t", "short", "/dev/../etc/shadow"),
    ("-H", "-i", "-l", "selftest", "-j", "-d", "sat", "/dev/../etc/shadow"),
])
def test_gefaehrliche_smartctl_formen_werden_abgelehnt(args):
    assert not _erlaubt(SMARTCTL, *args)
