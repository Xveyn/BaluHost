"""Ein unlesbares Array reisst die RAID-Statusantwort nicht mehr mit (#570).

`_build_array` ruft `mdadm --detail` mit check=True. Scheitert das fuer EIN
Array -- ein gerade entferntes Geraet, oder ein Name, den die verengten
sudoers-Regeln nicht abdecken --, brach bisher die gesamte Statusabfrage ab:
der Nutzer sah gar keine Arrays statt eines fehlerhaften.

Aufgefallen ist das beim Verengen der sudoers-Regeln: dort ist die Namensform
auf md0..md999 begrenzt, und die Frage "was passiert mit einem bestehenden
Array ausserhalb dieser Form" hatte bis dahin keine gute Antwort.
"""
import subprocess
from unittest.mock import MagicMock

import pytest

from app.schemas.system import RaidSpeedLimits
from app.services.hardware.raid.mdadm_backend import MdadmRaidBackend
from app.services.hardware.raid.parsing import MdstatInfo


def _backend(monkeypatch, *, arrays: dict, kaputt: set[str]) -> MdadmRaidBackend:
    backend = object.__new__(MdadmRaidBackend)
    backend._lsblk_available = False

    monkeypatch.setattr(MdadmRaidBackend, "_read_mdstat", lambda self: arrays)
    monkeypatch.setattr(MdadmRaidBackend, "_scan_arrays", lambda self: [])
    monkeypatch.setattr(MdadmRaidBackend, "_get_disk_type_map", lambda self: {})
    monkeypatch.setattr(MdadmRaidBackend, "_read_speed_limits",
                        lambda self: RaidSpeedLimits(minimum=1000, maximum=200000))

    # Der Fehler wird NICHT in _build_array injiziert, sondern dort, wo er real
    # entsteht: subprocess.run wirft CalledProcessError, das echte _run wandelt
    # ihn in RuntimeError um. Damit laeuft der Pfad, den die Produktion nimmt --
    # eine Attrappe um _build_array herum haette die Umwandlung uebersprungen.
    def _subprocess_run(cmd, **kw):
        ziel = cmd[-1] if isinstance(cmd, (list, tuple)) else str(cmd)
        if any(f"/dev/{name}" == ziel for name in kaputt):
            raise subprocess.CalledProcessError(
                returncode=1, cmd=cmd,
                stderr=f"mdadm: cannot open {ziel}: No such file or directory",
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0,
            stdout="Raid Level : raid1\nState : clean\n", stderr="",
        )

    monkeypatch.setattr("app.services.hardware.raid.mdadm_backend.subprocess.run",
                        _subprocess_run)
    monkeypatch.setattr(MdadmRaidBackend, "_resolve_array_size", lambda *a, **k: 1024)
    monkeypatch.setattr(MdadmRaidBackend, "_resolve_progress", lambda *a, **k: None)
    monkeypatch.setattr(MdadmRaidBackend, "_parse_devices", lambda *a, **k: [])
    monkeypatch.setattr(MdadmRaidBackend, "_read_sync_action", lambda *a, **k: None)
    return backend


def test_ein_kaputtes_array_nimmt_die_gesunden_nicht_mit(monkeypatch):
    backend = _backend(
        monkeypatch,
        arrays={"md1": MdstatInfo(members=["sda1", "sdb"]),
                "md_data": MdstatInfo(members=["sdc"])},
        kaputt={"md_data"},
    )

    antwort = backend.get_status()

    namen = {a.name for a in antwort.arrays}
    assert namen == {"md1", "md_data"}, "beide Arrays muessen sichtbar bleiben"
    gesund = next(a for a in antwort.arrays if a.name == "md1")
    assert gesund.level == "raid1"


def test_das_kaputte_array_wird_als_unbekannt_gemeldet_statt_verschwiegen(monkeypatch):
    backend = _backend(
        monkeypatch,
        arrays={"md_data": MdstatInfo(members=["sdc", "sdd"])},
        kaputt={"md_data"},
    )

    antwort = backend.get_status()

    array = antwort.arrays[0]
    assert array.name == "md_data"
    assert array.status == "unknown"
    assert array.level == "unknown"
    # Was /proc/mdstat hergibt, bleibt sichtbar -- die Mitglieder stehen dort
    # auch dann, wenn mdadm --detail scheitert.
    assert [d.name for d in array.devices] == ["sdc", "sdd"]


def test_ohne_fehler_bleibt_alles_wie_vorher(monkeypatch):
    backend = _backend(
        monkeypatch,
        arrays={"md0": MdstatInfo(members=["sda"]), "md1": MdstatInfo(members=["sdb"])},
        kaputt=set(),
    )

    antwort = backend.get_status()

    assert [a.name for a in antwort.arrays] == ["md0", "md1"]
    assert all(a.status != "unknown" for a in antwort.arrays)
