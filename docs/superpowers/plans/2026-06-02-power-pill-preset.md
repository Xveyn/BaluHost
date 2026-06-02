# Power-Pille: Profil/Preset anzeigen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Topbar-Power-Pille zeigt statt nur der Intensitätsstufe (idle/low/medium/surge) das, was die CPU tatsächlich steuert: das aktive Preset + die Stufe, bzw. im Dynamic Mode den Kernel-Governor.

**Architecture:** Reine Backend-Änderung an genau einem Collector (`collect_power` in `backend/app/services/status_bar/collectors.py`). Drei Zustände: (1) Dynamic Mode → `Dynamisch · <governor>`; (2) Profil-Modus + aktives Preset → `<Preset> · <Stufe>`; (3) Profil-Modus ohne Preset → `<Stufe>` (heutiges Verhalten). Die generische `<Pill>`-Komponente rendert `label` bereits — kein Frontend-Code.

**Tech Stack:** Python 3, pytest, `unittest.mock` (`AsyncMock`/`MagicMock`/`patch`). FastAPI-Service-Layer.

**Spec:** `docs/superpowers/specs/2026-06-02-power-pill-profile-design.md`

---

## File Structure

| Datei | Verantwortung | Aktion |
|---|---|---|
| `backend/app/services/status_bar/collectors.py` | `collect_power` — mappt `get_power_status()` auf einen Pill-State-Dict | Modify (nur die `collect_power`-Funktion, Zeilen 30-46) |
| `backend/tests/services/test_status_bar_collectors.py` | Unit-Tests der Collectoren | Modify (5 neue Tests anhängen) |

Keine neuen Dateien. Kein Frontend-, Schema-, Migrations- oder i18n-Key-Change.

**Wichtige Mock-Hinweise (gelten für alle Tests unten):**
- `collect_power` importiert `get_power_manager` **lokal** aus `app.services.power.manager` → dort patchen: `patch("app.services.power.manager.get_power_manager", return_value=mgr)`.
- `get_power_status` ist `async` → `mgr.get_power_status = AsyncMock(return_value=status)`.
- Preset-Name **nicht** via `MagicMock(name="Balanced")` setzen (`name` ist ein reserviertes MagicMock-Kwarg, das den Mock benennt statt das Attribut). Stattdessen: `preset = MagicMock(); preset.name = "Balanced"`.
- `MagicMock()` liefert für nicht gesetzte Attribute neue Mock-Objekte (truthy). Felder, die `None`/`False` sein müssen (`current_profile`, `active_preset`, `dynamic_mode_enabled`), **explizit** im Konstruktor setzen.

`AsyncMock`, `MagicMock`, `patch` sind in der Testdatei bereits importiert (`from unittest.mock import AsyncMock, MagicMock, patch`).

---

## Task 1: Profil-Modus — Preset + Stufe (und Fallback)

Stellt `collect_power` von „nur Stufe" auf „Preset · Stufe" um, mit Fallback auf reine Stufe, wenn kein Preset aktiv ist. Der Dynamic-Mode-Sonderfall kommt in Task 2.

**Files:**
- Modify: `backend/app/services/status_bar/collectors.py:30-46`
- Test: `backend/tests/services/test_status_bar_collectors.py` (anhängen)

- [ ] **Step 1: Failing tests anhängen**

Ans Ende von `backend/tests/services/test_status_bar_collectors.py` anfügen:

```python
# ── power ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_power_pill_preset_and_level():
    from app.services.status_bar import collectors
    preset = MagicMock()
    preset.name = "Balanced"
    status = MagicMock(
        dynamic_mode_enabled=False,
        current_profile=MagicMock(value="surge"),
        active_preset=preset,
    )
    mgr = MagicMock()
    mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        result = await collectors.collect_power(MagicMock(), "admin")
    assert result["label"] == "Balanced · Surge"
    assert result["tone"] == "info"
    assert result["icon"] == "Zap"
    assert "value" not in result


@pytest.mark.asyncio
async def test_power_pill_no_preset_fallback():
    from app.services.status_bar import collectors
    status = MagicMock(
        dynamic_mode_enabled=False,
        current_profile=MagicMock(value="surge"),
        active_preset=None,
    )
    mgr = MagicMock()
    mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        result = await collectors.collect_power(MagicMock(), "admin")
    assert result["label"] == "Surge"
    assert "value" not in result


@pytest.mark.asyncio
async def test_power_pill_silent_without_profile():
    from app.services.status_bar import collectors
    status = MagicMock(
        dynamic_mode_enabled=False,
        current_profile=None,
        active_profile=None,
        profile=None,
    )
    mgr = MagicMock()
    mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        assert await collectors.collect_power(MagicMock(), "admin") is None
```

- [ ] **Step 2: Tests laufen lassen — erwarte FAIL**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py -k power -v --no-cov`
Expected: `test_power_pill_preset_and_level` schlägt fehl (heutiger Code zeigt `label == "Surge"`, kein Preset). Die anderen beiden können je nach Altverhalten passen — entscheidend ist der rote `preset_and_level`-Test.

- [ ] **Step 3: `collect_power` umsetzen**

In `backend/app/services/status_bar/collectors.py` die bestehende `collect_power`-Funktion (Zeilen 30-46) **vollständig** ersetzen durch:

```python
# ── power ────────────────────────────────────────────────────────────
@_safe()
async def collect_power(db: Session, role: str) -> Optional[dict]:
    from app.services.power.manager import get_power_manager
    status = await get_power_manager().get_power_status()

    profile = getattr(status, "current_profile", None)
    if not profile:
        return None
    # PowerProfile is a str-enum; its `.value` (e.g. "surge") is the level text.
    level = str(getattr(profile, "value", profile)).replace("_", " ").title()

    # Active preset (e.g. "Balanced"/"Performance") maps each level to MHz —
    # it's what actually configures the CPU, so show it as the prominent part.
    preset = getattr(status, "active_preset", None)
    preset_name = getattr(preset, "name", None) if preset else None
    label = f"{preset_name} · {level}" if preset_name else level
    return {"kind": "state", "tone": "info", "label": label, "icon": "Zap"}
```

- [ ] **Step 4: Tests laufen lassen — erwarte PASS**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py -k power -v --no-cov`
Expected: `test_power_pill_preset_and_level`, `test_power_pill_no_preset_fallback`, `test_power_pill_silent_without_profile` PASS. (`test_power_pill_dynamic_*` existieren noch nicht.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/status_bar/collectors.py backend/tests/services/test_status_bar_collectors.py
git commit -m "feat(power): show active preset + level in power status pill"
```

---

## Task 2: Dynamic-Mode-Sonderfall — Modus + Governor

Wenn Dynamic Mode aktiv ist, regelt der Kernel-Governor direkt; Preset/Stufe sind eingefroren und irreführend. Die Pille zeigt dann `Dynamisch · <governor>`.

**Files:**
- Modify: `backend/app/services/status_bar/collectors.py` (`collect_power`, Dynamic-Branch ergänzen)
- Test: `backend/tests/services/test_status_bar_collectors.py` (anhängen)

- [ ] **Step 1: Failing tests anhängen**

Ans Ende von `backend/tests/services/test_status_bar_collectors.py` anfügen:

```python
@pytest.mark.asyncio
async def test_power_pill_dynamic_mode_with_governor():
    from app.services.status_bar import collectors
    status = MagicMock(
        dynamic_mode_enabled=True,
        dynamic_mode_config=MagicMock(governor="schedutil"),
    )
    mgr = MagicMock()
    mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        result = await collectors.collect_power(MagicMock(), "admin")
    assert result["label"] == "Dynamisch · schedutil"
    assert result["tone"] == "info"
    assert result["icon"] == "Zap"


@pytest.mark.asyncio
async def test_power_pill_dynamic_mode_no_config():
    from app.services.status_bar import collectors
    status = MagicMock(
        dynamic_mode_enabled=True,
        dynamic_mode_config=None,
    )
    mgr = MagicMock()
    mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        result = await collectors.collect_power(MagicMock(), "admin")
    assert result["label"] == "Dynamisch"
```

- [ ] **Step 2: Tests laufen lassen — erwarte FAIL**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py -k "dynamic_mode" -v --no-cov`
Expected: Beide FAIL — der aktuelle Code ignoriert `dynamic_mode_enabled` und bildet `label` aus dem (gemockten) `current_profile`/`active_preset`, statt `"Dynamisch · schedutil"`/`"Dynamisch"`.

- [ ] **Step 3: Dynamic-Branch ergänzen**

In `backend/app/services/status_bar/collectors.py`, in `collect_power`, **direkt nach** der Zeile `status = await get_power_manager().get_power_status()` und **vor** `profile = getattr(...)` einfügen:

```python
    # Dynamic mode: the kernel governor controls the CPU directly — the demand
    # profile and preset are frozen and no longer reflect what's running, so we
    # surface the mode + governor instead of a stale "preset · level".
    if getattr(status, "dynamic_mode_enabled", False):
        gov = getattr(getattr(status, "dynamic_mode_config", None), "governor", None)
        label = f"Dynamisch · {gov}" if gov else "Dynamisch"
        return {"kind": "state", "tone": "info", "label": label, "icon": "Zap"}
```

Die Funktion lautet danach vollständig:

```python
# ── power ────────────────────────────────────────────────────────────
@_safe()
async def collect_power(db: Session, role: str) -> Optional[dict]:
    from app.services.power.manager import get_power_manager
    status = await get_power_manager().get_power_status()

    # Dynamic mode: the kernel governor controls the CPU directly — the demand
    # profile and preset are frozen and no longer reflect what's running, so we
    # surface the mode + governor instead of a stale "preset · level".
    if getattr(status, "dynamic_mode_enabled", False):
        gov = getattr(getattr(status, "dynamic_mode_config", None), "governor", None)
        label = f"Dynamisch · {gov}" if gov else "Dynamisch"
        return {"kind": "state", "tone": "info", "label": label, "icon": "Zap"}

    profile = getattr(status, "current_profile", None)
    if not profile:
        return None
    # PowerProfile is a str-enum; its `.value` (e.g. "surge") is the level text.
    level = str(getattr(profile, "value", profile)).replace("_", " ").title()

    # Active preset (e.g. "Balanced"/"Performance") maps each level to MHz —
    # it's what actually configures the CPU, so show it as the prominent part.
    preset = getattr(status, "active_preset", None)
    preset_name = getattr(preset, "name", None) if preset else None
    label = f"{preset_name} · {level}" if preset_name else level
    return {"kind": "state", "tone": "info", "label": label, "icon": "Zap"}
```

- [ ] **Step 4: Tests laufen lassen — erwarte PASS**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py -k power -v --no-cov`
Expected: Alle 5 Power-Tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/status_bar/collectors.py backend/tests/services/test_status_bar_collectors.py
git commit -m "feat(power): show dynamic-mode governor in power status pill"
```

---

## Task 3: Regression-Verifikation

Sicherstellen, dass die gesamte Status-Bar-Test-Suite (Collectoren + Service + Routes) weiterhin grün ist.

**Files:** keine Änderung.

- [ ] **Step 1: Volle Status-Bar-Suite**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py tests/services/test_status_bar_service.py tests/api/test_status_bar_routes.py -q --no-cov`
Expected: Alle Tests PASS (vorher 31 in collectors; jetzt 36 dort + Service/Routes unverändert grün).

- [ ] **Step 2: Falls rot — Service-/Routes-Erwartungen prüfen**

`test_status_bar_service.py` aggregiert Collectoren. Sollte ein dortiger Test eine konkrete Power-Pill-`label` erwartet haben (z.B. `"Surge"`), die jetzt `"Balanced · Surge"` lautet, den Test an das neue Verhalten anpassen (nicht das Feature). Andernfalls keine Aktion.

---

## Manual Smoketest (nach Deploy)

1. Als Admin einloggen, Power-Pille in der Topbar aktiviert (`System Control → System → Status Bar`).
2. Energy-Tab öffnen, ein anderes Preset aktivieren → Pille zeigt innerhalb von ~10s `<NeuerPreset> · <Stufe>`.
3. Dynamic Mode einschalten → Pille wechselt zu `Dynamisch · <governor>` (z.B. `Dynamisch · schedutil`).
4. Dynamic Mode ausschalten → Pille zeigt wieder `<Preset> · <Stufe>`.

## Out of Scope (laut Spec)

- Lokalisierung der Stufen-Namen (bleiben englisch title-case)
- Dedizierter Frontend-`PowerPill.tsx`-Renderer
- MHz/Live-Frequenz in der Pille
- Tooltip mit Preset-Details (browser-natives `title` aus `label` genügt)
