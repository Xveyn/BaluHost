# Loop-Device mdadm Integration-CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Echte mdadm-Integrationstests gegen Loop-Device-RAID-Arrays auf `ubuntu-latest` etablieren und den toten/zahnlosen `raid-mdadm-selfhosted.yml` ablösen.

**Architecture:** Eine neue Pytest-Suite (`test_mdadm_loopback.py`) treibt `MdadmRaidBackend()` direkt gegen ein echtes raid1 aus zwei Loop-Devices (create→status→delete und degrade→rebuild→finalize). Sie ist via Env-Var gegated und läuft nur im neuen GitHub-hosted Workflow `raid-mdadm-loopback.yml`. Der self-hosted Workflow, ein Duplikat-Mock-Test und die Security-Doku werden entsprechend bereinigt.

**Tech Stack:** GitHub Actions (ubuntu-latest), Python/pytest, mdadm, losetup, Linux loop devices.

**Spec:** `docs/superpowers/specs/2026-06-09-mdadm-loopback-ci-design.md`

---

## Wichtiger Kontext für den ausführenden Entwickler

- **Die Loopback-Tests laufen NICHT lokal (Windows/Dev) und nicht im normalen CI.** Sie sind per `BALUHOST_MDADM_LOOPBACK`-Env-Var gegated und werden überall sonst übersprungen. Lokale Verifikation = „die Datei wird sauber gesammelt und als *skipped* gemeldet". Der echte Grün-Beweis ist der CI-Job auf dem PR (Task 4).
- pytest immer aus `backend/` ausführen: `cd backend && python -m pytest ...`.
- `MdadmRaidBackend` wird **direkt** instanziiert (nicht über `app.services.hardware.raid.api`, dessen Modul-Level-`_backend` in Tests via `is_dev_mode` zum DevBackend würde).
- Repo läuft mit `core.autocrlf=true`; LF↔CRLF-Warnungen bei `git commit`/`git add` sind erwartbar und unkritisch.
- `.github/workflows/` und `.claude/rules/ci-cd-security.md` sind CODEOWNERS-geschützt (@Xveyn) — der PR wird owner-getaggt, das ist beabsichtigt.

---

## Task 1: Loop-Device Integration-Test-Suite

**Files:**
- Create: `backend/tests/raid/test_mdadm_loopback.py`

- [ ] **Step 1: Test-Datei anlegen**

Erstelle `backend/tests/raid/test_mdadm_loopback.py` mit EXAKT diesem Inhalt:

```python
"""Real mdadm integration tests against loop-device backed RAID arrays.

These exercise MdadmRaidBackend against an actual mdadm/kernel (create, status,
degrade, rebuild, finalize, delete) on throwaway loop devices — no production
disks involved. They run ONLY in the dedicated `raid-mdadm-loopback.yml` CI job
(ubuntu-latest), gated by the BALUHOST_MDADM_LOOPBACK env var, and are skipped
everywhere else (dev machines, normal CI).
"""
import os
import subprocess
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.hardware.raid import MdadmRaidBackend
from app.schemas.system import (
    CreateArrayRequest,
    DeleteArrayRequest,
    RaidSimulationRequest,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("BALUHOST_MDADM_LOOPBACK"),
    reason="loopback mdadm integration runs only in the dedicated CI job",
)

ARRAY_NAME = "md0"
ARRAY_PATH = f"/dev/{ARRAY_NAME}"


def _sudo(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sudo", "-n", *args], check=check, capture_output=True, text=True
    )


@pytest.fixture
def loop_raid(tmp_path):
    """Provision two loop devices; guarantee teardown of array + loops + files."""
    loops: list[str] = []
    files: list[Path] = []
    # Defensive: the array name must be free on this (ephemeral) host.
    assert not Path(ARRAY_PATH).exists(), f"{ARRAY_PATH} already exists on this host"
    try:
        for i in range(2):
            f = tmp_path / f"disk{i}.img"
            subprocess.run(["truncate", "-s", "128M", str(f)], check=True)
            files.append(f)
            res = _sudo("losetup", "--find", "--show", str(f))
            loops.append(res.stdout.strip())
        yield loops
    finally:
        # Stop array if present, zero superblocks, detach loops, remove files.
        _sudo("mdadm", "--stop", ARRAY_PATH, check=False)
        for lp in loops:
            _sudo("mdadm", "--zero-superblock", lp, check=False)
            _sudo("losetup", "-d", lp, check=False)
        for f in files:
            try:
                f.unlink()
            except OSError:
                pass


def _array_named(status, name):
    return next((a for a in status.arrays if a.name == name), None)


def test_create_status_delete_lifecycle(loop_raid, monkeypatch):
    monkeypatch.setattr(settings, "raid_assume_clean_by_default", True, raising=False)
    backend = MdadmRaidBackend()
    loop_a, loop_b = loop_raid

    backend.create_array(
        CreateArrayRequest(name=ARRAY_NAME, level="raid1", devices=[loop_a, loop_b])
    )

    status = backend.get_status()
    arr = _array_named(status, ARRAY_NAME)
    assert arr is not None, f"{ARRAY_NAME} not found in status after create"
    assert arr.level == "raid1"
    assert arr.status == "optimal"
    assert len(arr.devices) == 2

    backend.delete_array(DeleteArrayRequest(array=ARRAY_NAME, force=True))

    assert _array_named(backend.get_status(), ARRAY_NAME) is None


def test_degrade_rebuild_finalize_cycle(loop_raid, monkeypatch):
    monkeypatch.setattr(settings, "raid_assume_clean_by_default", True, raising=False)
    backend = MdadmRaidBackend()
    loop_a, loop_b = loop_raid

    backend.create_array(
        CreateArrayRequest(name=ARRAY_NAME, level="raid1", devices=[loop_a, loop_b])
    )
    assert _array_named(backend.get_status(), ARRAY_NAME).status == "optimal"

    backend.degrade(RaidSimulationRequest(array=ARRAY_NAME, device=loop_a))
    degraded = _array_named(backend.get_status(), ARRAY_NAME)
    assert degraded is not None
    assert degraded.status != "optimal"

    backend.rebuild(RaidSimulationRequest(array=ARRAY_NAME, device=loop_a))
    backend.finalize(RaidSimulationRequest(array=ARRAY_NAME))

    healed = _array_named(backend.get_status(), ARRAY_NAME)
    assert healed is not None
    assert healed.status == "optimal"

    backend.delete_array(DeleteArrayRequest(array=ARRAY_NAME, force=True))
```

- [ ] **Step 2: Lokale Skip-Verifikation (kann nicht real laufen)**

Run: `cd backend && python -m pytest tests/raid/test_mdadm_loopback.py -v`
Expected: **`2 skipped`** (Gate `BALUHOST_MDADM_LOOPBACK` ist nicht gesetzt). Wichtig: keine Collection-/Import-Fehler — die Datei muss sauber importieren (alle Imports existieren: `MdadmRaidBackend` aus `app.services.hardware.raid`, die drei Schemas aus `app.schemas.system`). Wenn stattdessen Errors beim Sammeln erscheinen, Importpfade prüfen.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/raid/test_mdadm_loopback.py
git commit -m "test(raid): real loop-device mdadm integration suite (#185)"
```

---

## Task 2: GitHub-Workflow anlegen, self-hosted ablösen, Security-Doku aktualisieren

**Files:**
- Create: `.github/workflows/raid-mdadm-loopback.yml`
- Delete: `.github/workflows/raid-mdadm-selfhosted.yml`
- Modify: `.claude/rules/ci-cd-security.md`

- [ ] **Step 1: Neuen Workflow anlegen**

Erstelle `.github/workflows/raid-mdadm-loopback.yml` mit EXAKT diesem Inhalt:

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
      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.11'
      - name: Install mdadm
        run: |
          sudo apt-get update -qq
          sudo apt-get install -y -qq mdadm
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

- [ ] **Step 2: Toten self-hosted Workflow löschen**

```bash
git rm .github/workflows/raid-mdadm-selfhosted.yml
```

- [ ] **Step 3: Security-Doku — Layer-2-Tabellenzeile ersetzen**

In `.claude/rules/ci-cd-security.md` die Zeile (aktuell Zeile 39):
```
| `raid-mdadm-selfhosted.yml` | **`self-hosted, linux, mdadm`** | `workflow_dispatch` only |
```
ersetzen durch:
```
| `raid-mdadm-loopback.yml` | `ubuntu-latest` | `pull_request` (paths: raid), `workflow_dispatch` |
```

- [ ] **Step 4: Security-Doku — Stale-label-gap-Absatz ersetzen**

Den Absatz (aktuell Zeile 54):
```
**Stale-label gap (2026-05-12)**: `raid-mdadm-selfhosted.yml` requires the `mdadm` label, but the `BaluNode` runner only has `self-hosted, Linux, X64`. The workflow currently cannot acquire a runner and would hang indefinitely if dispatched. Either add the `mdadm` label to `BaluNode` (config in `/opt/actions-runner/.runner` or via the GitHub UI) or change the workflow to drop the label requirement.
```
ersetzen durch:
```
**Resolved (2026-06-09)**: the dead `raid-mdadm-selfhosted.yml` (which required a non-existent `mdadm` runner label and only ran mock tests anyway) was retired and replaced by `raid-mdadm-loopback.yml` on `ubuntu-latest`. Real mdadm coverage now runs on ephemeral GitHub-hosted VMs against loop-device arrays — no self-hosted runner, no production-disk risk (issue #185).
```

- [ ] **Step 5: Security-Doku — Known-Gap #7 ersetzen**

Den Known-Gaps-Eintrag #7:
```
7. **`raid-mdadm-selfhosted.yml` runner label mismatch** — Workflow requires `mdadm` label, `BaluNode` runner only has `self-hosted, Linux, X64`. Not a security risk (workflow simply cannot acquire a runner); flagged for cleanup if/when the workflow is needed.
```
ersetzen durch:
```
7. **`raid-mdadm-selfhosted.yml` runner label mismatch — resolved (2026-06-09)** — The dead workflow was retired and replaced by `raid-mdadm-loopback.yml` on `ubuntu-latest` (loop-device mdadm tests). No self-hosted runner is involved, so the label-mismatch gap no longer exists (issue #185).
```

- [ ] **Step 6: YAML-Syntax prüfen + keine Restverweise**

Run: `cd backend && python -c "import yaml; yaml.safe_load(open(r'../.github/workflows/raid-mdadm-loopback.yml', encoding='utf-8')); print('yaml ok')"`
Expected: `yaml ok`

Run: `python -c "import pathlib; hits=[p for p in pathlib.Path('.').rglob('*') if p.is_file() and p.suffix in {'.yml','.yaml','.md'} and 'raid-mdadm-selfhosted' in p.read_text(encoding='utf-8', errors='ignore')]; print(hits or 'no references left')"`
Expected: `no references left` (keine Datei referenziert den alten Workflow mehr).

- [ ] **Step 7: Commit**

Die Löschung aus Step 2 ist bereits gestaged. Jetzt nur Anlage + Doku-Edit hinzufügen und committen:
```bash
git add .github/workflows/raid-mdadm-loopback.yml .claude/rules/ci-cd-security.md
git status   # erwartet: new file loopback.yml, deleted selfhosted.yml, modified ci-cd-security.md
git commit -m "ci(raid): replace dead self-hosted mdadm workflow with ubuntu-latest loopback (#185)"
```

---

## Task 3: Duplikat-Mock-Test bereinigen

**Files:**
- Delete: `backend/tests/raid/test_mdadm_integration.py`
- Modify: `backend/tests/raid/test_mdadm_integration_local.py`

Kontext: `test_mdadm_integration.py` und `test_mdadm_integration_local.py` sind inhaltlich near-identische Mock-Tests (beide faken `backend._run`). Sie testen keine echte Hardware. Das Duplikat wird entfernt; der Überlebende bekommt einen klarstellenden Docstring, damit niemand „integration" für echte mdadm-Abdeckung hält.

- [ ] **Step 1: Duplikat löschen**

```bash
git rm backend/tests/raid/test_mdadm_integration.py
```

- [ ] **Step 2: Klarstellenden Docstring in den Überlebenden setzen**

In `backend/tests/raid/test_mdadm_integration_local.py` ist die erste Zeile aktuell `import json`. Füge GANZ OBEN (vor `import json`) diesen Modul-Docstring ein:

```python
"""Parsing-level tests for MdadmRaidBackend using a fake `_run` (no real mdadm).

Despite the historical "integration" filename, these inject canned subprocess
output and verify parsing only — no mdadm, sudo, or block devices are touched.
Real hardware coverage lives in `test_mdadm_loopback.py` (ubuntu-latest CI).
"""
```

- [ ] **Step 3: RAID-Suite weiterhin grün (Duplikat-Entfernung bricht nichts)**

Run: `cd backend && python -m pytest tests/raid -v`
Expected: alle Tests PASS, **`test_mdadm_loopback.py` als skipped** (2 skipped), **kein** `test_mdadm_integration.py` mehr in der Sammlung, `test_mdadm_integration_local.py` weiterhin grün.

- [ ] **Step 4: Commit**

Die Löschung aus Step 1 ist bereits gestaged. Jetzt den Docstring-Edit hinzufügen und committen:
```bash
git add backend/tests/raid/test_mdadm_integration_local.py
git status   # erwartet: deleted test_mdadm_integration.py, modified test_mdadm_integration_local.py
git commit -m "test(raid): drop duplicate mock 'integration' test, clarify the survivor (#185)"
```

---

## Task 4: PR + CI-Verifikation (der eigentliche Grün-Beweis)

**Files:** keine Änderung — Push, PR und Beobachtung des neuen Workflows.

- [ ] **Step 1: Branch pushen**

```bash
git push -u origin fix/185-mdadm-loopback-ci
```

- [ ] **Step 2: PR gegen main öffnen**

PR-Body via Write-Tool in eine Datei schreiben (here-strings scheitern in beiden Shells), dann:
```bash
gh pr create --base main --head fix/185-mdadm-loopback-ci \
  --title "ci(raid): loop-device mdadm integration on ubuntu-latest, retire dead self-hosted workflow (#185)" \
  --body-file <body-file>
```
Body-Inhalt: Summary (echter mdadm-Loopback-CI ersetzt toten/zahnlosen self-hosted Workflow), Verweis auf Recon (Prod-Runner=sven mit unrestricted sudo mdadm + Live-md1 → self-hosted zu riskant), und Test-Plan-Checkliste inkl. „CI-Job `raid-mdadm-loopback` muss grün sein und `2 passed` zeigen (nicht `2 skipped`)".

- [ ] **Step 3: Den neuen Workflow-Lauf prüfen**

Run: `gh pr checks <PR#> --watch` (oder `gh run list --workflow=raid-mdadm-loopback.yml -L 3`).
Expected: Job `RAID mdadm loopback integration` läuft auf dem PR (paths-Filter greift, da der PR `backend/tests/raid/**` + den Workflow ändert) und ist **grün**.

- [ ] **Step 4: Sicherstellen, dass die Tests REAL liefen (nicht skipped)**

Run: `gh run view <run-id> --log | python -c "import sys; s=sys.stdin.read(); print('PASSED 2' if '2 passed' in s else ('SKIPPED!' if 'skipped' in s and '2 passed' not in s else 'CHECK MANUALLY'))"`
Expected: `PASSED 2`. Falls `SKIPPED!` → die Env-Var `BALUHOST_MDADM_LOOPBACK` greift nicht; Workflow-`env:`-Block prüfen. Falls Tests fehlschlagen → Logs lesen (häufige Ursachen: `mdadm` nicht im PATH → `is_supported()` False → `MdadmRaidBackend()` RuntimeError; oder `sudo -n` ohne NOPASSWD — auf ubuntu-latest aber gegeben).

> Dieser Task ist die einzige Stelle, an der die Loopback-Tests tatsächlich ausgeführt werden. Tasks 1–3 konnten sie lokal nur als *skipped* sehen.

---

## Notes
- **Branch:** `fix/185-mdadm-loopback-ci` (von `origin/main`); Spec-Commit `9d720b44` liegt vor.
- **PR-Ziel:** `main`. Der Loopback-Workflow ist bewusst **kein** required Branch-Protection-Check (erst Stabilität beobachten); Required bleiben `backend-tests`, `frontend-build`.
- **Determinismus:** `--assume-clean` (via `settings.raid_assume_clean_by_default`) verhindert Resync beim Create; `finalize` nutzt `mdadm --wait` statt Sleeps.
- **Bewusst weggelassen:** `get_available_disks`-Assertion im Lifecycle-Test (lsblk meldet Loop-Devices uneinheitlich); harte Zusicherung ist der Array-Status. SMART/Fan/WireGuard-Integration sind Folgearbeit außerhalb #185.
