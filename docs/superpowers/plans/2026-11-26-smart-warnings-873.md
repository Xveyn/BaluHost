# SMART-Warnungen wieder melden (#873) — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `_check_smart_for_notifications` meldet `FAILED`-Platten, Attribute im Zustand `FAILING` und umgelagerte Sektoren wieder — für jede Platte, auch wenn die Prüfung einer anderen scheitert.

**Architecture:** Eine Funktion in `backend/app/services/hardware/smart/api.py` liest die richtigen Felder von `SmartAttribute` (`status`, `raw` statt der nicht existierenden `when_failed`, `raw_value`) und fängt Fehler je Gerät statt um die ganze Schleife. Dazu die ersten Tests dieser Funktion.

**Tech Stack:** Python 3.13, Pydantic v2, pytest.

**Spec:** Issue [#873](https://github.com/Xveyn/BaluHost/issues/873) (kein Design-Dokument; das Issue beschreibt Defekt, Nachweis und Fix-Vorschlag).

## Global Constraints

- **Benachrichtigungstexte und Ereignistypen bleiben unverändert:** `emit_smart_failure_sync(device.name, details=f"Status: FAILED, Modell: {device.model}")`, `emit_smart_warning_sync(device.name, details=f"Attribut '{attr.name}' ist im FAILING-Zustand")`, `emit_smart_warning_sync(device.name, details=f"{count} reallocated Sektoren erkannt")`. Kein Umstieg auf `EventType.SMART_REALLOCATED` (existiert, ist aber nirgends verdrahtet — eigene Entscheidung, nicht dieser Fix).
- **Ablauf je Gerät wie heute:** `status == "FAILED"` → Ausfall melden, Attribute dieses Geräts nicht weiter prüfen. Sonst höchstens eine `FAILING`-Warnung (erstes Attribut) und höchstens eine Reallocated-Warnung (erstes Attribut mit „reallocated" im Namen, ohne Rücksicht auf Groß-/Kleinschreibung, Zahl > 0).
- **Felder von `SmartAttribute`** (`backend/app/schemas/system.py`): `id, name, value, worst, threshold, raw: str, status: str`. Der Collector (`smart/collector.py:130-139`) setzt `status = "FAILING"`, wenn smartctl ein `when_failed` liefert, sonst `"OK"`; `raw` ist der Rohwert als Text (`"8"`). Die Zahl ist das erste durch Leerzeichen getrennte Token von `raw`; ist es keine ganze Zahl, wird für dieses Attribut nichts gemeldet und nichts geworfen.
- **Fehler je Gerät:** eine Ausnahme bei einem Gerät wird gefangen, mit `logger.warning` samt Gerätename protokolliert, und die Schleife läuft mit dem nächsten Gerät weiter. Nicht mehr auf DEBUG schlucken — genau das hat den Defekt monatelang versteckt.
- **Die Emit-Funktionen werden weiter innerhalb der Funktion importiert** (`from app.services.notifications.events import …`); Tests patchen sie unter `app.services.notifications.events`.
- **Tests auf BaluNode nur in der Sandbox:** `cd backend && bwrap --dev-bind / / --tmpfs /dev/shm --unshare-pid --proc /proc --die-with-parent --chdir "$PWD" -- /home/sven/projects/BaluHost/backend/.venv/bin/python -m pytest …`. Ruff vor dem Commit: `cd backend && /home/sven/projects/BaluHost/backend/.venv/bin/python -m ruff check app tests`. Kein `sudo`.

## Review Focus

1. **Platte mit Gesamtstatus `FAILED`, die nach einer SATA-Platte mit `Reallocated_Sector_Ct` kommt** — muss gemeldet werden (heute nicht). Test: `test_all_three_problems_are_reported`.
2. **Rohwert, der keine Zahl ist** (`"n/a"`, leer) — keine Meldung, keine Ausnahme, nächste Platte wird geprüft. Test: `test_unparseable_raw_is_skipped_quietly`.
3. **Eine Meldung wirft** (z. B. DB-Fehler beim Speichern der Benachrichtigung) — die übrigen Platten werden trotzdem geprüft. Test: `test_error_on_one_device_does_not_stop_the_others`.
4. **Reallocated = 0** (Normalfall, auch alle Mock-Platten) — keine Meldung. Test: `test_zero_reallocated_sectors_is_silent`.
5. **NVMe ohne ATA-Attribute** (nur `Temperature`, `Available_Spare`) — keine Meldung, keine Ausnahme. Test: `test_nvme_without_ata_attributes_is_silent`.

---

### Task 1: Prüfung reparieren und erstmals testen

**Files:**
- Modify: `backend/app/services/hardware/smart/api.py:20-56` (`_check_smart_for_notifications`)
- Create: `backend/tests/services/test_smart_notifications.py`

**Interfaces:**
- Produces: `_check_smart_for_notifications(status: SmartStatusResponse) -> None` — Signatur unverändert; Aufrufer `get_smart_status()` (Z. 92, 110) bleiben unberührt.

- [ ] **Step 1: Tests schreiben** (`backend/tests/services/test_smart_notifications.py`)

Hilfen im Testmodul: `_device(name, status, attrs)` baut ein `SmartDevice` (Pflichtfelder: `name, model, serial, temperature, status, capacity_bytes, used_bytes, used_percent, mount_point, last_self_test, attributes`; für die Tests unerhebliche Felder mit festen Werten wie `model="m"`, `serial="s"`, `temperature=30`, `capacity_bytes=1`, Rest `None`), `_attr(name, raw="0", status="OK", id=5)` baut ein `SmartAttribute` (`value=100, worst=100, threshold=10`), `_status(*devices)` baut ein `SmartStatusResponse(checked_at=datetime.now(timezone.utc), devices=[...])`. Eine Fixture `emitted` patcht beide Emit-Funktionen per `monkeypatch.setattr("app.services.notifications.events.emit_smart_failure_sync", …)` bzw. `…emit_smart_warning_sync` und sammelt `(kind, disk, details)` in einer Liste (`kind` = `"FAILURE"` / `"WARNING"`).

```python
def test_all_three_problems_are_reported(emitted):
    _check_smart_for_notifications(_status(
        _device("/dev/sda", "PASSED", [_attr("Reallocated_Sector_Ct", raw="8")]),
        _device("/dev/sdb", "FAILED", []),
        _device("/dev/sdc", "PASSED", [_attr("Raw_Read_Error_Rate", status="FAILING", id=1)]),
    ))
    assert emitted == [
        ("WARNING", "/dev/sda", "8 reallocated Sektoren erkannt"),
        ("FAILURE", "/dev/sdb", "Status: FAILED, Modell: m"),
        ("WARNING", "/dev/sdc", "Attribut 'Raw_Read_Error_Rate' ist im FAILING-Zustand"),
    ]

def test_failed_device_skips_its_attribute_checks(emitted):
    _check_smart_for_notifications(_status(
        _device("/dev/sda", "FAILED", [_attr("Reallocated_Sector_Ct", raw="8")]),
    ))
    assert [e[0] for e in emitted] == ["FAILURE"]

def test_zero_reallocated_sectors_is_silent(emitted):
    _check_smart_for_notifications(_status(_device("/dev/sda", "PASSED", [_attr("Reallocated_Sector_Ct", raw="0")])))
    assert emitted == []

def test_reallocated_count_is_the_first_token(emitted):
    _check_smart_for_notifications(_status(_device("/dev/sda", "PASSED", [_attr("Reallocated_Event_Count", raw="12 (Average 3)")])))
    assert emitted == [("WARNING", "/dev/sda", "12 reallocated Sektoren erkannt")]

def test_unparseable_raw_is_skipped_quietly(emitted):
    _check_smart_for_notifications(_status(
        _device("/dev/sda", "PASSED", [_attr("Reallocated_Sector_Ct", raw="n/a")]),
        _device("/dev/sdb", "FAILED", []),
    ))
    assert emitted == [("FAILURE", "/dev/sdb", "Status: FAILED, Modell: m")]

def test_nvme_without_ata_attributes_is_silent(emitted):
    _check_smart_for_notifications(_status(_device("/dev/nvme0", "PASSED", [
        _attr("Temperature", raw="35", id=194), _attr("Available_Spare", raw="100", id=5),
    ])))
    assert emitted == []

def test_error_on_one_device_does_not_stop_the_others(monkeypatch, emitted, caplog):
    # Ausfall-Meldung für sdb wirft; sdc muss trotzdem geprüft werden.
    def failing_failure(disk, details=""):
        raise RuntimeError("notification store down")
    monkeypatch.setattr("app.services.notifications.events.emit_smart_failure_sync", failing_failure)
    _check_smart_for_notifications(_status(
        _device("/dev/sdb", "FAILED", []),
        _device("/dev/sdc", "PASSED", [_attr("Raw_Read_Error_Rate", status="FAILING", id=1)]),
    ))
    assert ("WARNING", "/dev/sdc", "Attribut 'Raw_Read_Error_Rate' ist im FAILING-Zustand") in emitted
    assert any("/dev/sdb" in r.getMessage() and r.levelname == "WARNING" for r in caplog.records)
```

- [ ] **Step 2: Ausführen, muss fehlschlagen**

Run: `cd backend && bwrap … -- /home/sven/projects/BaluHost/backend/.venv/bin/python -m pytest tests/services/test_smart_notifications.py -v -p no:cacheprovider`
Expected: FAIL in `test_all_three_problems_are_reported` (leere Liste), `test_reallocated_count_is_the_first_token`, `test_unparseable_raw_is_skipped_quietly`, `test_error_on_one_device_does_not_stop_the_others`; die stillen Fälle (`test_zero_…`, `test_nvme_…`, `test_failed_device_…`) können schon grün sein — sie halten fest, dass der Umbau nichts Neues meldet.

- [ ] **Step 3: `_check_smart_for_notifications` umbauen** — je Gerät ein eigener `try`/`except Exception` mit `logger.warning("SMART notification check failed for %s: %s", device.name, exc)`; `attr.status == "FAILING"` statt `getattr(attr, "when_failed", None) == "FAILING_NOW"`; `attr.raw` statt `attr.raw_value`; Zahl = `int(attr.raw.split()[0])`, `ValueError`/`IndexError` → für dieses Attribut nichts melden. Der äußere `try` bleibt nur um den Import der Emit-Funktionen (`logger.warning` bei Fehlschlag).

- [ ] **Step 4: Ausführen, alles grün; Ruff; volle Suite**

Run: `cd backend && bwrap … -- … -m pytest tests/services/test_smart_notifications.py tests/raid/test_system_health_smart.py -v -p no:cacheprovider`, dann `… -m ruff check app tests`, dann die volle Suite `… -m pytest -n 6 --no-cov -q -p no:cacheprovider`
Expected: alles passed; volle Suite mit derselben Anzahl Fehlschläge wie die Baseline (siehe Ledger), keine neuen.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/hardware/smart/api.py backend/tests/services/test_smart_notifications.py
git commit -m "fix(smart): Warnungsprüfung liest status/raw und prüft jede Platte einzeln (#873)"
```

### Abschluss

- [ ] PR `fix/smart-warnings-873` → `main`, `Closes #873`. Im Text: Nachweis aus dem Issue (drei Geräte, 0 Meldungen vorher), dass Texte/Ereignistypen unverändert sind, und dass `EventType.SMART_REALLOCATED` weiterhin unbenutzt ist.
- [ ] Nach dem Deploy: nur verifizierbar, wenn eine Platte tatsächlich Werte > 0 hat — im Journal nach `SMART notification check failed` schauen (darf nicht auftauchen).
