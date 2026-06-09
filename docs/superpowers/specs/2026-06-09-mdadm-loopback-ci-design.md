# Spec: Loop-Device mdadm Integration-CI (#185)

**Datum:** 2026-06-09
**Branch:** `fix/185-mdadm-loopback-ci` (von `origin/main`)
**Issue:** #185 — *ci: kein Hardware-in-the-loop-CI; raid-mdadm-selfhosted.yml mit totem Runner-Label*

## Problem

`raid-mdadm-selfhosted.yml` ist **doppelt kaputt**:
1. **Tot:** verlangt Runner-Label `mdadm`, das kein Runner hat (`BaluNode` = `self-hosted,Linux,X64,prod`) → hängt beim Dispatch.
2. **Zahnlos:** fährt `pytest -k raid`, das ausschließlich Mock-Tests trifft. `test_mdadm_integration.py` und `test_mdadm_integration_local.py` sind fast identische Duplikate, die `backend._run` mocken — **kein echtes mdadm, kein sudo, keine Block-Devices**. Ein grüner Check suggeriert Hardware-Abdeckung, die es nicht gibt.

Der echte mdadm-Pfad (`create/delete/degrade/rebuild`, `_run` prependet `sudo -n mdadm`) ist nur **manuell auf einer Maschine** validiert.

## Server-Recon-Befunde (BaluNode, 2026-06-09)

- Prod-Runner läuft als **`sven`** (`User=sven`, `ExecStart=/opt/actions-runner/runsvc.sh`).
- `sven` hat **unrestricted** `NOPASSWD: /sbin/mdadm`, `/usr/sbin/mdadm`, `/usr/sbin/smartctl` — **kein `losetup`**.
- `/proc/mdstat`: **laufendes Produktions-Array `md1`** (raid1, `sda`+`sdb1`, `[2/2] [UU]`). Personalities `[raid1…raid10]` geladen, `/dev/loop-control` vorhanden.

**Schlussfolgerung:** Ein echter RAID-CI auf BaluNode wäre gefährlich (ein Test-Bug könnte via `sudo mdadm` das Live-Array `md1` zerstören) **und** unnötig (echte Disks sind nicht nötig, nur Root + Loop-Devices). → Pivot auf ephemeren GitHub-Runner.

## Designentscheidung

**Loop-Device mdadm-Integrationstests auf `ubuntu-latest`.** Ephemere VM mit passwortlosem `sudo`, `losetup`, `mdadm`; keine Produktionsdaten; PR-sicher. Der bisherige self-hosted-Workflow wird **abgelöst** (gelöscht), nicht nur das Label geflickt.

### Nicht-Ziele (Out of Scope)
- Kein Test auf realer BaluNode-Hardware (bewusst verworfen wegen Live-`md1`-Risiko; siehe Recon).
- Keine neuen sudoers auf irgendeinem self-hosted Runner.
- Keine SMART/Fan/WireGuard-Integrationstests (eigene Folgearbeit; #185 fokussiert RAID/mdadm als Pilot).
- Kein Eintrag als *required* Branch-Protection-Check (Required bleiben `backend-tests`, `frontend-build`).

## Architektur

### Neue Test-Suite: `backend/tests/raid/test_mdadm_loopback.py`
Instanziiert `MdadmRaidBackend()` **direkt** (nicht über `api.py` — dessen `_backend` wird beim Import via `is_dev_mode` zum DevBackend gewählt; der direkte Weg testet unzweideutig den echten Pfad).

Modul-Gate: läuft **nur**, wenn die Env-Var `BALUHOST_MDADM_LOOPBACK=1` gesetzt ist (vom Workflow). Auf Dev-Maschinen / im normalen CI wird die Datei komplett übersprungen:
```python
pytestmark = pytest.mark.skipif(
    not os.environ.get("BALUHOST_MDADM_LOOPBACK"),
    reason="loopback mdadm integration runs only in the dedicated CI job",
)
```

**Fixture `loop_raid` (function-scope):** provisioniert zwei Loop-Devices und garantiert Teardown (auch bei Fehlschlag):
1. Zwei 128 MiB Backing-Files via `truncate` in einem `tmp_path`.
2. `sudo losetup --find --show <file>` → `/dev/loopN` (beide).
3. yield die zwei Loop-Pfade.
4. Teardown (in `finally`): `sudo mdadm --stop /dev/md0` (best-effort), `sudo mdadm --zero-superblock <loop>` je Device (best-effort), `sudo losetup -d <loop>` je Device, Files entfernen.

Vor Setup wird sichergestellt, dass `/dev/md0` frei ist (sonst klarer Skip/Fail) und `MdadmRaidBackend.is_supported()` True ist.

**Determinismus:** `settings.raid_assume_clean_by_default` wird per `monkeypatch` auf `True` gesetzt, damit `create_array` `--assume-clean` anhängt → kein initialer Resync → Array sofort `optimal`. Der Degrade/Rebuild-Test nutzt `finalize` (`mdadm --wait`) statt Sleeps.

### Tests (alle gegen das echte Loop-Array)

**`test_create_status_delete_lifecycle(loop_raid, monkeypatch)`**
- `backend.create_array(CreateArrayRequest(name="md0", level="raid1", devices=[loopA, loopB]))`
- `status = backend.get_status()` → genau ein Array `md0`, `level == "raid1"`, `status == "optimal"`, 2 Devices.
- `disks = backend.get_available_disks()` → die Loop-Devices erscheinen als `in_raid=True` (best-effort; falls lsblk Loops anders meldet, nur auf Array-Status prüfen).
- `backend.delete_array(DeleteArrayRequest(array="md0", force=True))`
- `backend.get_status()` → kein `md0` mehr.

**`test_degrade_rebuild_finalize_cycle(loop_raid, monkeypatch)`**
- create wie oben.
- `backend.degrade(RaidSimulationRequest(array="md0", device=loopA))` → `get_status` zeigt Array als `degraded` (oder ein Device `failed`/entfernt).
- `backend.rebuild(RaidSimulationRequest(array="md0", device=loopA))`
- `backend.finalize(RaidSimulationRequest(array="md0"))` → wartet via `mdadm --wait`, danach `status == "optimal"`.
- delete wie oben.

### Neuer Workflow: `.github/workflows/raid-mdadm-loopback.yml`
```yaml
name: RAID mdadm loopback integration

on:
  pull_request:
    paths:
      - 'backend/app/services/hardware/raid/**'
      - 'backend/tests/raid/**'
      - '.github/workflows/raid-mdadm-loopback.yml'
  workflow_dispatch: {}

permissions:
  contents: read

jobs:
  mdadm-loopback:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: '3.11'
      - name: Install mdadm
        run: sudo apt-get update && sudo apt-get install -y mdadm
      - name: Install backend (dev extras)
        working-directory: backend
        run: python -m pip install -e .[dev]
      - name: Run mdadm loopback integration tests
        working-directory: backend
        env:
          BALUHOST_MDADM_LOOPBACK: '1'
        run: |
          export PATH="/usr/sbin:/sbin:$PATH"
          python -m pytest tests/raid/test_mdadm_loopback.py -v
```
`ubuntu-latest` (GitHub-hosted) — keine self-hosted-Layer-Betroffenheit. pytest läuft als normaler Runner-User; Root nur per-Command via `sudo` (Fixture) bzw. `sudo -n mdadm` (Backend).

### Aufräumen: Duplikat-„Integration"-Tests
`test_mdadm_integration.py` und `test_mdadm_integration_local.py` sind near-identische Mock-Tests. **`test_mdadm_integration.py` wird gelöscht**; der Überlebende `test_mdadm_integration_local.py` bekommt einen klarstellenden Modul-Docstring („uses a fake `_run`; real mdadm coverage lives in `test_mdadm_loopback.py`"). Keine Test-Logik geht verloren (Inhalt ist identisch).

### Workflow-Ablösung + Doku
- `.github/workflows/raid-mdadm-selfhosted.yml` **löschen**.
- `.claude/rules/ci-cd-security.md` aktualisieren:
  - Layer-2-Tabelle: Zeile `raid-mdadm-selfhosted.yml` → `raid-mdadm-loopback.yml` (`ubuntu-latest`, `pull_request` + `workflow_dispatch`).
  - „Stale-label gap (2026-05-12)" Absatz → als behoben markieren/entfernen (Workflow retired).
  - Known Gaps #7 (Label-Mismatch) → als resolved markieren.

CODEOWNERS: `/.github/workflows/` ist generisch owner-getaggt; Datei-Löschung + -Neuanlage sind abgedeckt, keine CODEOWNERS-Änderung nötig.

## Betroffene Dateien
- **Create** `backend/tests/raid/test_mdadm_loopback.py`
- **Create** `.github/workflows/raid-mdadm-loopback.yml`
- **Delete** `.github/workflows/raid-mdadm-selfhosted.yml`
- **Delete** `backend/tests/raid/test_mdadm_integration.py`
- **Modify** `backend/tests/raid/test_mdadm_integration_local.py` (klarstellender Docstring)
- **Modify** `.claude/rules/ci-cd-security.md`

## Verifikation
- **Lokal (Windows/Dev):** `python -m pytest tests/raid -v` → die neue Loopback-Datei wird übersprungen (Gate); bestehende RAID-Tests bleiben grün; das gelöschte Duplikat reduziert keine echte Abdeckung.
- **CI (der eigentliche Beweis):** Branch-PR triggert `raid-mdadm-loopback.yml`; der Job muss grün sein und in den Logs zeigen, dass die Tests **nicht** übersprungen wurden (real ausgeführt) — d. h. `2 passed`, nicht `2 skipped`.
- **YAML-Lint:** `raid-mdadm-loopback.yml` parst sauber.
- **Doku-Konsistenz:** keine Verweise auf `raid-mdadm-selfhosted.yml` mehr im Repo.

## Risiken / Notizen
- **Flakiness:** `--assume-clean` + `mdadm --wait` eliminieren Resync-Timing. Falls `get_available_disks` Loop-Devices nicht wie erwartet meldet (lsblk-Eigenheiten bei Loops), wird diese Assertion tolerant gehalten — der Array-Status ist die harte Zusicherung.
- **`/dev/md0`-Kollision:** auf ephemerer ubuntu-latest-VM existiert kein md-Array; Fixture prüft trotzdem defensiv.
- **Required-Check:** bewusst NICHT als required gesetzt (erst Stabilität beobachten).
