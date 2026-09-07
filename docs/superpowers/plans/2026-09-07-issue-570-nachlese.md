# Nachlese GPU-Lüfterakustik (#570) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die acht schreibtischfähigen Befunde aus #570 beheben — vier Backend-/Testlücken, zwei Frontend-Härtungen, ein Kopplungstest, eine Doku-Korrektur.

**Architecture:** Keine neue Struktur. Jeder Punkt ist eine lokale Änderung an vorhandenem Code, jeweils mit einem Test, der ohne die Änderung fehlschlägt. Zwei Punkte sind reine Testlücken (das Verhalten stimmt heute) — dort ist der Test das Ergebnis, nicht der Fix.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2.0 / pytest, React 18 / TypeScript / Vitest / Testing Library.

**Spec:** Issue #570 (<https://github.com/Xveyn/BaluHost/issues/570>), Punkte 2, 3, 6, 7, 9, 10, 11, 12. Der Entwurf des zugrundeliegenden Features steht in `docs/superpowers/specs/2026-09-06-gpu-fan-acoustics-design.md`.

## Global Constraints

- **Nicht im Umfang:** Punkt 1 (fan_id am Endpunkt), 4 (Event-Loop, gehört zu #300), 5 (Sudoers-Verengung, braucht Feldmessung), 8 (Task-Nummern-Sweep, eigener PR). Diese vier bleiben in #570 offen — nicht nebenbei mitfixen.
- **Sprache:** Code-Kommentare und Testnamen auf Deutsch ohne Umlaute (`ue`, `ae`, `oe`), passend zum umgebenden Bestand in `fan_gpu_acoustics*.py`. Commit-Nachrichten deutsch, Präfix `fix(fans):` bzw. `test(fans):` bzw. `docs(fans):`, jeweils mit `(#570)`.
- **Type hints required on all functions** (`.claude/rules/backend/coding-style.md`).
- **Die volle Backend-Suite gehört der CI, nicht dieser Sitzung** — sie hängt unter Windows. Lokal läuft je Aufgabe nur die genannte Testdatei plus am Ende `python -m pytest -k "acoustics or fan_runtime" --no-cov -q`.
- **Frontend-Gates vor dem PR:** `npx eslint .` (0 Fehler) und `npm run build` — nicht nur `tsc --noEmit`.
- Branch: `fix/issue-570-nachlese`, PR gegen `main`.

---

### Task 1: `_competing_manager` prüft den nicht-auskommentierten Schlüssel (#570 Punkt 2)

**Files:**
- Modify: `backend/app/api/routes/fans.py:1085-1093`
- Test: `backend/tests/test_fan_acoustics_competing_manager.py` (neu)

**Interfaces:**
- Consumes: nichts aus anderen Aufgaben.
- Produces: `_competing_manager() -> Optional[str]` bleibt unverändert in Signatur und Rückgabewerten (`"lact"` oder `None`).

Heute reicht das blosse Vorkommen der Zeichenkette `pmfw_options` irgendwo in `/etc/lact/config.yaml`, um LACT als zweiten Verwalter zu melden — ein auskommentierter Block löst die Warnung fälschlich aus. Ein YAML-Parser wäre unverhältnismässig; geprüft wird zeilenweise auf den Schlüssel.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

Erstelle `backend/tests/test_fan_acoustics_competing_manager.py`:

```python
"""Erkennung eines zweiten Verwalters der Akustik-Knoten (#570 Punkt 2).

Ein auskommentierter pmfw_options-Block ist keine Konkurrenz -- LACT liest
ihn nicht, also darf BaluHost deswegen nicht warnen.
"""
from pathlib import Path

from app.api.routes import fans as fans_module


def _lact_config(tmp_path: Path, text: str, monkeypatch) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(text, encoding="utf-8")
    monkeypatch.setattr(fans_module, "LACT_CONFIG_PATH", cfg)


def test_ein_aktiver_block_meldet_lact(tmp_path, monkeypatch):
    _lact_config(tmp_path, "gpus:\n  1002:744C:\n    pmfw_options:\n      acoustic_limit: 3000\n", monkeypatch)
    assert fans_module._competing_manager() == "lact"


def test_ein_auskommentierter_block_meldet_nichts(tmp_path, monkeypatch):
    _lact_config(tmp_path, "gpus:\n  1002:744C:\n    # pmfw_options:\n    #   acoustic_limit: 3000\n", monkeypatch)
    assert fans_module._competing_manager() is None


def test_eingerueckt_auskommentiert_meldet_ebenfalls_nichts(tmp_path, monkeypatch):
    _lact_config(tmp_path, "gpus:\n      #pmfw_options:\n", monkeypatch)
    assert fans_module._competing_manager() is None


def test_ein_nachgestellter_kommentar_hebt_den_schluessel_nicht_auf(tmp_path, monkeypatch):
    _lact_config(tmp_path, "    pmfw_options:  # von BaluHost uebernommen\n", monkeypatch)
    assert fans_module._competing_manager() == "lact"


def test_eine_fehlende_datei_meldet_nichts(tmp_path, monkeypatch):
    monkeypatch.setattr(fans_module, "LACT_CONFIG_PATH", tmp_path / "gibt-es-nicht.yaml")
    assert fans_module._competing_manager() is None


def test_eine_datei_in_latin1_macht_den_get_nicht_kaputt(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_bytes(b"pmfw_options:\n# Kommentar mit \xfc\n")
    monkeypatch.setattr(fans_module, "LACT_CONFIG_PATH", cfg)
    assert fans_module._competing_manager() in ("lact", None)
```

- [ ] **Step 2: Lauf gegen den alten Code**

Run: `cd backend ; python -m pytest tests/test_fan_acoustics_competing_manager.py --no-cov -q`
Expected: FAIL — `test_ein_auskommentierter_block_meldet_nichts` und `test_eingerueckt_auskommentiert_meldet_ebenfalls_nichts` liefern `"lact"` statt `None`.

- [ ] **Step 3: Die Prüfung umstellen**

Ersetze in `backend/app/api/routes/fans.py` den Rumpf von `_competing_manager`:

```python
def _competing_manager() -> Optional[str]:
    # Zeilenweise statt als Teilstring: ein auskommentierter Block enthaelt
    # das Wort ebenfalls, und LACT liest ihn nicht (#570).
    try:
        if not LACT_CONFIG_PATH.exists():
            return None
        for line in LACT_CONFIG_PATH.read_text().splitlines():
            if line.lstrip().startswith("pmfw_options"):
                return "lact"
    except (OSError, ValueError):
        # ValueError deckt UnicodeDecodeError mit ab: eine von Hand
        # geschriebene Datei in Latin-1 darf den GET nicht zur 500 machen.
        pass
    return None
```

- [ ] **Step 4: Test erneut laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_acoustics_competing_manager.py --no-cov -q`
Expected: 6 passed

- [ ] **Step 5: Ruff**

Run: `cd backend ; python -m ruff check app/api/routes/fans.py tests/test_fan_acoustics_competing_manager.py`
Expected: `All checks passed!`

- [ ] **Step 6: Committen**

```bash
git add backend/app/api/routes/fans.py backend/tests/test_fan_acoustics_competing_manager.py
git commit -m "fix(fans): auskommentierte pmfw_options nicht als zweiten Verwalter melden (#570)"
```

---

### Task 2: Typannotationen in `fan_runtime_store.py` (#570 Punkt 6)

**Files:**
- Modify: `backend/app/services/power/fan_runtime_store.py:31,52`

**Interfaces:**
- Consumes: nichts.
- Produces: `read_write_permission(db: Session) -> Optional[bool]`, `publish_write_permission(db: Session, may_write: bool) -> bool` — Verhalten unverändert, nur annotiert.

Die Schwesterdatei `fan_gpu_acoustics_store.py` annotiert bereits `db: Session` (Zeilen 46–162) und importiert `from sqlalchemy.orm import Session`. Diese Datei zieht nach. Rein mechanisch, kein Verhaltenswechsel — deshalb ohne eigenen Test, aber mit einer Typprüfung als Beleg.

- [ ] **Step 1: Import ergänzen**

In `backend/app/services/power/fan_runtime_store.py`, unter `from sqlalchemy import select`:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session
```

- [ ] **Step 2: Beide Signaturen annotieren**

```python
def read_write_permission(db: Session) -> Optional[bool]:
```

```python
def publish_write_permission(db: Session, may_write: bool) -> bool:
```

Die Docstrings bleiben unverändert.

- [ ] **Step 3: Prüfen, dass keine weitere Funktion in der Datei unannotiert ist**

Run: `cd backend ; python -c "import ast,sys; t=ast.parse(open('app/services/power/fan_runtime_store.py',encoding='utf-8').read()); print([f.name for f in t.body if isinstance(f,ast.FunctionDef) and any(a.annotation is None for a in f.args.args)])"`
Expected: `[]`

- [ ] **Step 4: Ruff und die vorhandenen Tests der Datei**

Run: `cd backend ; python -m ruff check app/services/power/fan_runtime_store.py ; python -m pytest -k "fan_runtime or permission" --no-cov -q`
Expected: `All checks passed!` und alle Tests bestanden

- [ ] **Step 5: Committen**

```bash
git add backend/app/services/power/fan_runtime_store.py
git commit -m "fix(fans): db-Parameter in fan_runtime_store annotieren (#570)"
```

---

### Task 3: Grenzwerttest für `write_acoustic` (#570 Punkt 7)

**Files:**
- Modify: `backend/tests/test_fan_gpu_acoustics_write.py` (anfügen)

**Interfaces:**
- Consumes: `write_acoustic(fan_ctrl_dir: Path, name: str, value: int, write: WriteFn) -> bool` und die vorhandenen Helfer `_card_tree`, `_recording_write` aus derselben Datei.
- Produces: nichts für spätere Aufgaben.

`write_acoustic` prüft `node.minimum <= value <= node.maximum`. Getestet ist bisher nur der klar aussenliegende Fall (200 gegen einen Bereich, der bei 105 endet). Ob die Grenzen selbst als **eingeschlossen** gelten, prüft nichts — ein `<` statt `<=` bliebe unbemerkt. Der Bereich im Testbaum ist `25 105` (Konstante `TARGET_TEMPERATURE` am Dateikopf).

- [ ] **Step 1: Die vier Grenzfälle anfügen**

Ans Ende von `backend/tests/test_fan_gpu_acoustics_write.py`, hinter den vorhandenen `write_acoustic`-Tests und vor den `resolve_restores`-Tests:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("value", [25, 105])
async def test_die_grenzen_selbst_sind_eingeschlossen(tmp_path, value):
    """OD_RANGE meldet 25..105 -- beide Enden sind gueltige Werte.

    Ohne diesen Test bliebe ein < statt <= unbemerkt: der aussenliegende
    Fall (200) faellt bei beiden Fassungen durch (#570).
    """
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    calls = []

    ok = await write_acoustic(
        fan_ctrl, "fan_target_temperature", value,
        _recording_write(calls, applied=str(value), fan_ctrl=fan_ctrl),
    )

    assert ok is True
    assert calls == [
        ("fan_target_temperature", str(value)),
        ("fan_target_temperature", "c"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [24, 106])
async def test_ein_schritt_ausserhalb_der_grenzen_wird_abgelehnt(tmp_path, value):
    """Die Gegenprobe zum Test darueber: direkt neben der Grenze, nicht
    weit draussen. Es darf kein Write die Karte erreichen."""
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    calls = []

    ok = await write_acoustic(
        fan_ctrl, "fan_target_temperature", value, _recording_write(calls),
    )

    assert ok is False
    assert calls == []
```

- [ ] **Step 2: Lauf**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_write.py --no-cov -q`
Expected: alle bestanden (die vier neuen Fälle beschreiben das heutige, korrekte Verhalten — sie nageln es fest)

- [ ] **Step 3: Gegenprobe, dass der Test etwas misst**

Ändere in `backend/app/services/power/fan_gpu_acoustics.py` versuchsweise `if not node.minimum <= value <= node.maximum:` zu `if not node.minimum < value < node.maximum:` und lauf erneut.
Expected: `test_die_grenzen_selbst_sind_eingeschlossen` schlägt für beide Werte fehl. **Änderung danach zurücknehmen** (`git checkout -- backend/app/services/power/fan_gpu_acoustics.py`) und den Lauf aus Step 2 wiederholen, um den sauberen Stand zu belegen.

- [ ] **Step 4: Committen**

```bash
git add backend/tests/test_fan_gpu_acoustics_write.py
git commit -m "test(fans): Grenzen des gemeldeten Bereichs als eingeschlossen festnageln (#570)"
```

---

### Task 4: Den Startpfad an den weichen Loader binden (#570 Punkt 11)

**Files:**
- Modify: `backend/tests/test_fan_gpu_acoustics_apply.py` (anfügen)

**Interfaces:**
- Consumes: die Helfer `session_factory` (Fixture), `_service(session_factory, monkeypatch, *, primary=True)` und `_patch_module(monkeypatch, *, current: dict, written: list)` aus derselben Datei; `FanControlService.apply_acoustics()` liefert `Dict[str, bool]`.
- Produces: nichts für spätere Aufgaben.

`apply_acoustics` nimmt `load_acoustics_config_fail_soft` (`fan_control.py:418`). Die Store-Tests prüfen beide Loader einzeln, aber kein Test prüft, **welchen der Startpfad tatsächlich ruft**. Nähme jemand die harte Variante, würde eine kaputte Konfigurationszeile eine Ausnahme werfen; heute ist das doppelt abgesichert, weil `start()` den Aufruf in `try/except Exception` fasst — die Verdrahtung wäre also still verloren.

Der Test schreibt bewusst **unlesbares JSON** in die Singleton-Zeile: das ist der Fall, in dem `load_acoustics_config` `AcousticsConfigUnreadable` wirft.

- [ ] **Step 1: Den Test anfügen**

Ans Ende von `backend/tests/test_fan_gpu_acoustics_apply.py`:

```python
@pytest.mark.asyncio
async def test_eine_kaputte_konfigurationszeile_verhindert_den_start_nicht(
    session_factory, monkeypatch
):
    """Der Startpfad muss den WEICHEN Loader nehmen (#570).

    Nimmt er die harte Variante, wirft eine unlesbare Zeile
    AcousticsConfigUnreadable. Dass start() das heute in try/except faengt,
    macht die Verdrahtung nicht ueberfluessig -- es verbirgt nur ihren
    Verlust.
    """
    from app.models.fans import GpuFanAcousticsConfigDb

    with session_factory() as db:
        db.add(GpuFanAcousticsConfigDb(id=1, config_json="{kein gueltiges json"))
        db.commit()

    service = _service(session_factory, monkeypatch)
    written: list = []
    _patch_module(monkeypatch, current={}, written=written)

    result = await service.apply_acoustics()

    assert result == {}
    assert written == []
```

- [ ] **Step 2: Lauf**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_apply.py --no-cov -q`
Expected: alle bestanden

- [ ] **Step 3: Gegenprobe, dass der Test etwas misst**

Ändere in `backend/app/services/power/fan_control.py:418` versuchsweise `load_acoustics_config_fail_soft(db)` zu `load_acoustics_config(db)` (der Name ist in derselben Datei bereits importiert oder muss ergänzt werden) und lauf erneut.
Expected: der neue Test schlägt mit `AcousticsConfigUnreadable` fehl. **Änderung danach zurücknehmen** (`git checkout -- backend/app/services/power/fan_control.py`) und Step 2 wiederholen.

- [ ] **Step 4: Committen**

```bash
git add backend/tests/test_fan_gpu_acoustics_apply.py
git commit -m "test(fans): Startpfad an den weichen Konfigurations-Loader binden (#570)"
```

---

### Task 5: Kopplungstest der drei Knotenlisten (#570 Punkt 10)

**Files:**
- Test: `backend/tests/test_gpu_acoustics_node_lists.py` (neu)

**Interfaces:**
- Consumes: `ACOUSTIC_NODES: tuple[str, ...]` aus `app.services.power.fan_gpu_acoustics`; `GpuFanAcousticsValues` aus `app.schemas.gpu_fan_acoustics`; die Konstante `SETTABLE_NODES` in `client/src/components/fan-control/FirmwareFanNotice.tsx:26`.
- Produces: nichts für spätere Aufgaben.

Die Liste der setzbaren Knoten steht an drei Stellen. Die Dreiteilung ist bewusst so gebaut (das Frontend darf seine Liste nicht vom Backend beziehen) — was fehlt, ist ein Test, der sie gegeneinander hält. Ein fünfter Knoten auf Kernel 6.13+ verlangt sonst drei Änderungen, und wer eine vergisst, merkt es nicht.

**Muster:** identisch zu `backend/tests/test_amd_gpu_udev_rule.py`, das Vorlage und Installationsskript gegeneinander hält — eine bewusste Doppelung wird durch einen Test gekoppelt, nicht durch Zusammenlegen aufgelöst.

- [ ] **Step 1: Den Test schreiben**

Erstelle `backend/tests/test_gpu_acoustics_node_lists.py`:

```python
"""Die drei Listen der setzbaren Akustik-Knoten muessen deckungsgleich sein (#570).

Sie stehen bewusst dreimal: Backend-Erlaubnisliste, Pydantic-Schema und die
Frontend-Konstante, damit das Frontend seine Liste nicht vom Backend bezieht.
Was fehlte, war die Kopplung -- ein fuenfter Knoten (Kernel 6.13:
fan_zero_rpm_enable) verlangt drei Aenderungen, und wer eine vergisst, sieht
entweder keinen Regler oder einen still verworfenen PUT.
"""
import re
from pathlib import Path

from app.schemas.gpu_fan_acoustics import GpuFanAcousticsValues
from app.services.power.fan_gpu_acoustics import ACOUSTIC_NODES

TSX = (
    Path(__file__).resolve().parents[2]
    / "client" / "src" / "components" / "fan-control" / "FirmwareFanNotice.tsx"
)


def _frontend_nodes() -> list[str]:
    """SETTABLE_NODES aus der TSX-Datei lesen.

    Textlich statt ueber einen JS-Lauf: der Test soll in der Backend-Suite
    ohne node laufen. Findet der Ausdruck die Konstante nicht mehr, faellt
    das als leere Liste auf -- deshalb prueft der erste Test die Laenge.
    """
    block = re.search(r"const SETTABLE_NODES\s*=\s*\[(.*?)\]", TSX.read_text(encoding="utf-8"), re.S)
    if block is None:
        return []
    return re.findall(r"['\"]([a-z_]+)['\"]", block.group(1))


def test_die_frontend_liste_ist_ueberhaupt_auffindbar():
    """Schutz gegen einen vakuum-gruenen Test: findet der Ausdruck die
    Konstante nicht, waeren alle Vergleiche unten trivial erfuellt."""
    assert len(_frontend_nodes()) == len(ACOUSTIC_NODES)


def test_backend_erlaubnisliste_und_schema_stimmen_ueberein():
    assert set(ACOUSTIC_NODES) == set(GpuFanAcousticsValues.model_fields)


def test_frontend_liste_und_backend_erlaubnisliste_stimmen_ueberein():
    assert set(_frontend_nodes()) == set(ACOUSTIC_NODES)
```

- [ ] **Step 2: Lauf**

Run: `cd backend ; python -m pytest tests/test_gpu_acoustics_node_lists.py --no-cov -q`
Expected: 3 passed

- [ ] **Step 3: Gegenprobe, dass der Test etwas misst**

Füge in `client/src/components/fan-control/FirmwareFanNotice.tsx` der Konstante `SETTABLE_NODES` versuchsweise einen fünften Eintrag `'fan_zero_rpm_enable'` hinzu und lauf erneut.
Expected: `test_die_frontend_liste_ist_ueberhaupt_auffindbar` und `test_frontend_liste_und_backend_erlaubnisliste_stimmen_ueberein` schlagen fehl. **Änderung zurücknehmen** (`git checkout -- client/src/components/fan-control/FirmwareFanNotice.tsx`) und Step 2 wiederholen.

- [ ] **Step 4: Committen**

```bash
git add backend/tests/test_gpu_acoustics_node_lists.py
git commit -m "test(fans): die drei Listen der setzbaren Akustik-Knoten koppeln (#570)"
```

---

### Task 6: Regler während einer laufenden Anfrage sperren (#570 Punkt 3)

**Files:**
- Modify: `client/src/components/fan-control/FirmwareFanNotice.tsx:211`
- Test: `client/src/__tests__/components/fan-control/FirmwareFanNotice.test.tsx` (anfügen)

**Interfaces:**
- Consumes: der vorhandene State `acousticsBusy` (`FirmwareFanNotice.tsx:77`) und `managed[name]`.
- Produces: nichts für spätere Aufgaben.

`acousticsBusy` sperrt heute „Übernehmen" und „Zurücksetzen" (Zeilen 252, 262), nicht aber die vier `range`-Eingaben. Wer während der laufenden Anfrage zieht, sieht seinen Zug von der eintreffenden Antwort überschrieben — es sieht aus, als reagiere die Oberfläche nicht.

Das vorhandene Muster für so einen Test steht in derselben Datei ab Zeile 123 („deaktiviert Save und Reset, solange eine Anfrage laeuft"): die Antwort wird an ein von Hand aufgelöstes Promise gehängt, damit der laufende Zustand prüfbar ist. Lies diesen Test, bevor du den neuen schreibst, und baue ihn nach demselben Muster.

- [ ] **Step 1: Den fehlschlagenden Test anfügen**

```tsx
it('sperrt auch die Regler, solange eine Anfrage laeuft', async () => {
  // Ein VERWALTETER Knoten, sonst waere der Regler schon durch
  // !managed[name] gesperrt und der Test bewiese nichts -- dieselbe
  // Konstruktion wie in "zeigt einen bereits verwalteten Knoten als
  // markiert und bedienbar".
  const managedStatus = {
    ...FULL_STATUS,
    nodes: {
      ...FOUR_NODES,
      fan_target_temperature: { current: 95, minimum: 25, maximum: 105, desired: 78 },
    },
  };
  vi.mocked(getGpuAcoustics).mockResolvedValue(managedStatus);
  let resolvePut: (v: unknown) => void = () => {};
  vi.mocked(setGpuAcoustics).mockReturnValue(
    new Promise((res) => { resolvePut = res; }) as ReturnType<typeof setGpuAcoustics>,
  );
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);

  const slider = await screen.findByRole('slider', { name: /fan_target_temperature/ });
  expect(slider).not.toBeDisabled();

  fireEvent.click(screen.getByText('system:fanControl.gpu.acoustics.save'));

  await waitFor(() => expect(slider).toBeDisabled());

  resolvePut(managedStatus);
  await waitFor(() => expect(slider).not.toBeDisabled());
});
```

`FOUR_NODES` und `FULL_STATUS` sind vorhandene Konstanten der Testdatei; in `FULL_STATUS` ist **kein** Knoten verwaltet (`desired: null` bei allen vieren), deshalb der eigene `managedStatus`. Die Abfrage über `getByRole('slider', …)` ist das Muster, das die Datei bereits benutzt.

- [ ] **Step 2: Lauf gegen den alten Code**

Run: `cd client ; npx vitest run src/__tests__/components/fan-control/FirmwareFanNotice.test.tsx`
Expected: FAIL — der Regler bleibt während der Anfrage bedienbar.

- [ ] **Step 3: Die Sperre ergänzen**

In `client/src/components/fan-control/FirmwareFanNotice.tsx`, am `range`-Input:

```tsx
                    disabled={!managed[name] || acousticsBusy}
```

- [ ] **Step 4: Lauf**

Run: `cd client ; npx vitest run src/__tests__/components/fan-control/FirmwareFanNotice.test.tsx`
Expected: alle bestanden

- [ ] **Step 5: Committen**

```bash
git add client/src/components/fan-control/FirmwareFanNotice.tsx client/src/__tests__/components/fan-control/FirmwareFanNotice.test.tsx
git commit -m "fix(fans): Akustik-Regler waehrend einer laufenden Anfrage sperren (#570)"
```

---

### Task 7: 503 nur mit passendem `detail` als Konfigurationsproblem melden (#570 Punkt 9)

**Files:**
- Modify: `client/src/components/fan-control/FirmwareFanNotice.tsx:63-68`
- Test: `client/src/__tests__/components/fan-control/FirmwareFanNotice.test.tsx` (anfügen)

**Interfaces:**
- Consumes: `isConfigUnavailable(err: unknown): boolean` in derselben Datei.
- Produces: `isConfigUnavailable` bleibt in Name und Signatur unverändert.

Heute erkennt `isConfigUnavailable` den Fall allein an der Statuszahl. 503 kommt aber auch von Nginx oder vom Upstream — etwa während eines Deploy-Neustarts. Wer in diesem Moment speichert, bekommt eine sachlich falsche Diagnose über seine Konfiguration.

Das Backend sendet in genau zwei Fällen eine 503, beide mit einem `detail`, das mit `GPU acoustics configuration` beginnt (`backend/app/api/routes/fans.py:1180` und `:1232`: `"GPU acoustics configuration is currently unreadable"` bzw. `"GPU acoustics configuration could not be saved"`). Ein Nginx-503 trägt HTML, kein solches `detail`.

- [ ] **Step 1: Den fehlschlagenden Test anfügen**

```tsx
it('meldet eine 503 vom Reverse-Proxy nicht als Konfigurationsproblem', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue(FULL_STATUS);
  vi.mocked(setGpuAcoustics).mockRejectedValue({
    response: { status: 503, data: '<html>503 Service Temporarily Unavailable</html>' },
  });
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);

  fireEvent.click(await screen.findByText('system:fanControl.gpu.acoustics.save'));

  const error = await screen.findByTestId('gpu-acoustics-error');
  expect(error.textContent).not.toContain('configUnavailable');
});
```

Der vorhandene Test „meldet eine 503 als Konfigurationsproblem, nicht als Hardware-Fehler" (Zeile 200) muss weiter bestehen — er schickt ein `detail` mit und deckt damit die andere Richtung ab.

- [ ] **Step 2: Lauf gegen den alten Code**

Run: `cd client ; npx vitest run src/__tests__/components/fan-control/FirmwareFanNotice.test.tsx`
Expected: FAIL — der Proxy-Fehler wird als `configUnavailable` gemeldet.

- [ ] **Step 3: Die Prüfung schärfen**

```tsx
// A 503 from the PUT means the stored configuration is unreadable or could
// not be saved — the card is not at fault, and the message must not read as
// if it were. Der Statuscode allein reicht dafuer nicht: 503 kommt auch vom
// Reverse-Proxy waehrend eines Deploy-Neustarts, und dann waere die
// Diagnose ueber die Konfiguration schlicht falsch (#570).
function isConfigUnavailable(err: unknown): boolean {
  const response = (err as { response?: { status?: number; data?: unknown } })?.response;
  if (response?.status !== 503) return false;
  const detail = (response.data as { detail?: unknown } | undefined)?.detail;
  return typeof detail === 'string' && detail.startsWith('GPU acoustics configuration');
}
```

- [ ] **Step 4: Lauf**

Run: `cd client ; npx vitest run src/__tests__/components/fan-control/FirmwareFanNotice.test.tsx`
Expected: alle bestanden, insbesondere beide 503-Tests

- [ ] **Step 5: Committen**

```bash
git add client/src/components/fan-control/FirmwareFanNotice.tsx client/src/__tests__/components/fan-control/FirmwareFanNotice.test.tsx
git commit -m "fix(fans): 503 nur mit passendem detail als Konfigurationsproblem deuten (#570)"
```

---

### Task 8: Betriebsdoku — der Fallback-Zweig umgeht den sudoers-Glob (#570 Punkt 12)

**Files:**
- Modify: `docs/deployment/AMD_GPU_PERMISSIONS.de.md:38-44`

**Interfaces:** keine.

Die Doku sagt heute ohne Einschränkung, das Backend falle bei `EACCES` auf `sudo -n tee` zurück und der sudoers-Eintrag für `/sys/class/hwmon/*` decke den Schreibpfad ab — die udev-Regel sei deshalb die Verbesserung, nicht die Voraussetzung.

Das gilt nur auf dem **Primärzweig** der Gerätepfad-Auflösung. `_device_from_hwmon` (`backend/app/services/power/fan_gpu_manual.py`) liefert dort `<hwmon>/device` **unaufgelöst**, der Pfad beginnt also mit `/sys/class/hwmon/` und fällt unter den sudoers-Glob (Wildcards in sudoers-**Argumenten** matchen `/`). Der Fallback-Zweig läuft über `hwmon_dir.resolve()` und liefert einen `/sys/devices/…`-Pfad — dort greift der Eintrag nicht, und ohne udev-Regel schlüge der Write wirklich mit `EACCES` fehl.

Auf BaluNode läuft der an der Hardware verifizierte Primärzweig; relevant ist das für fremde Hardware.

- [ ] **Step 1: Den Absatz ergänzen**

Ersetze in `docs/deployment/AMD_GPU_PERMISSIONS.de.md` den Satz, der mit „Das Backend fällt bei `EACCES` auf" beginnt, bis zum Ende des Absatzes durch:

```markdown
Das Backend fällt bei `EACCES` auf `sudo -n tee` zurück, und der vorhandene
sudoers-Eintrag für `/sys/class/hwmon/*` deckt den Schreibpfad ab — Wildcards
in sudoers-*Argumenten* matchen auch `/`, der Eintrag greift also bis in
`hwmonN/device/gpu_od/fan_ctrl/`. Die Werte greifen damit auch dann, wenn die
Knoten weiterhin `root:root 0644` tragen; die udev-Regel ist hier die
unprivilegierte Verbesserung, nicht die Voraussetzung.

**Diese Zusage gilt nur auf dem Primärzweig der Gerätepfad-Auflösung.**
`_device_from_hwmon()` (`backend/app/services/power/fan_gpu_manual.py`) liefert
dort `<hwmon>/device` unaufgelöst — der Pfad beginnt mit `/sys/class/hwmon/`
und fällt unter den Glob. Greift stattdessen der Fallback-Zweig (Aufwärtslauf
über den aufgelösten Pfad), liegt der Pfad unter `/sys/devices/…`, der
sudoers-Eintrag greift nicht, und ohne die udev-Regel schlägt der Write mit
`EACCES` fehl. Auf BaluNode läuft der an der Hardware verifizierte
Primärzweig; auf abweichender Hardware ist die udev-Regel deshalb unter
Umständen doch Voraussetzung (#570).
```

- [ ] **Step 2: Prüfen, dass der Rest des Abschnitts unberührt ist**

Run: `git diff --stat docs/deployment/AMD_GPU_PERMISSIONS.de.md`
Expected: genau eine Datei, ~10 Zeilen ergänzt, keine gelöschten Abschnitte ausser dem ersetzten Absatz

- [ ] **Step 3: Committen**

```bash
git add docs/deployment/AMD_GPU_PERMISSIONS.de.md
git commit -m "docs(fans): Grenze der sudo-tee-Zusage auf den Primaerzweig benennen (#570)"
```

---

## Abschluss

- [ ] **Gesamtlauf Backend**

Run: `cd backend ; python -m pytest -k "acoustics or fan_runtime or competing" --no-cov -q`
Expected: alle bestanden

- [ ] **Gesamtlauf Frontend plus Gates**

Run: `cd client ; npx vitest run ; npx eslint . ; npm run build`
Expected: Tests bestanden, 0 ESLint-Fehler, Build erfolgreich

- [ ] **PR öffnen**

Titel: `fix(fans): Nachlese der GPU-Luefterakustik -- acht Befunde aus #570`
Body: je Punkt eine Zeile mit Nummer aus #570 und was sich ändert; ausdrücklich vermerken, dass die Punkte 1, 4, 5 und 8 **offen bleiben** und warum (Punkt 4 gehört zu #300, Punkt 5 braucht eine Feldmessung, Punkt 8 wird ein eigener PR, Punkt 1 ist ohne zweite dGPU nicht auslösbar).
