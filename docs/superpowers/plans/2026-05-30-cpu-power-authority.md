# CPU Power Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BaluHost durchsetzt den CPU-Frequenz-Cap aus dem aktiven Preset (Re-Assert + Drift-Korrektur), wird alleinige Autorität (PPD stillgelegt) und hebt den Cap automatisch, sobald ein Allowlist-Programm/eine Spielsitzung läuft.

**Architecture:** Erweiterung des bestehenden `PowerManagerService` + Demand-System. Neuer 2-s-`_enforcement_loop` (primary-only) macht Re-Assert/Drift und Game-Session-Watch. Eine `ppd_authority`-Komponente maskt `power-profiles-daemon`. Eine `power_boost_rules`-Tabelle + lokale (Tauri-Channel) Endpoints konfigurieren die Allowlist. Frontend zeigt Live-Frequenz, Drift-Badge, Authority-Schalter, Allowlist-Editor, „Boost jetzt".

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (Mapped/mapped_column), Alembic, pytest/pytest-asyncio, psutil, React + TypeScript + Tailwind, i18next.

**Spec:** `docs/superpowers/specs/2026-05-30-cpu-power-authority-design.md`

---

## File Structure

**Backend — neu:**
- `backend/app/services/power/ppd_authority.py` — stop/mask/unmask/start power-profiles-daemon, Vorzustand merken.
- `backend/app/services/power/process_watcher.py` — psutil-Scan, Glob- + Game-Session-Erkennung, Hysterese.
- `backend/app/models/power_boost_rule.py` — `PowerBoostRule` ORM-Modell.
- `backend/alembic/versions/<rev>_add_power_boost_rules.py` — Migration + Seed-Regel.

**Backend — geändert:**
- `backend/app/services/power/manager.py` — `_enforcement_loop`, `_enforce_current_profile`, `_desired_config_for`, Drift-State, Boost-Override, Watcher-Anbindung, 400-Floor.
- `backend/app/services/power/cpu_protocol.py` + `cpu_dev_backend.py` + `cpu_linux_backend.py` — `read_enforcement_state()`.
- `backend/app/services/power/config_store.py` — Authority-Config laden/speichern, Boost-Rule-CRUD.
- `backend/app/models/power.py` → ergänzt um Authority-Felder ODER neue Singleton-Tabelle (Task 5).
- `backend/app/models/__init__.py` — Registrierung `PowerBoostRule`.
- `backend/app/schemas/power.py` — neue Schemas.
- `backend/app/api/routes/power.py` — neue Endpoints.
- `backend/app/services/power/__init__.py` — Exporte.

**Deploy:**
- `deploy/install/templates/` — sudoers-Snippet um vier `power-profiles-daemon`-Zeilen erweitern.

**Frontend:**
- `client/src/components/power/` — Authority-Schalter, Drift-Badge, Allowlist-Editor, Boost-now; Live-Frequenz-Fix in der Energy-Ansicht.
- `client/src/api/` — Power-API-Client erweitern.
- i18n de/en.

**Tests:**
- `backend/tests/services/test_power_enforcement.py`
- `backend/tests/services/test_process_watcher.py`
- `backend/tests/services/test_ppd_authority.py`
- `backend/tests/api/test_power_authority_routes.py`

---

# Phase 1 — Backend Core (Root-Cause-Fix: Cap durchsetzen)

Diese Phase allein behebt das gemeldete Problem (Cap wird durchgesetzt statt einmalig geschrieben) und ist eigenständig testbar/lieferbar.

## Task 1: Read-back-Helfer im CPU-Backend

**Files:**
- Modify: `backend/app/services/power/cpu_protocol.py`
- Modify: `backend/app/services/power/cpu_dev_backend.py`
- Modify: `backend/app/services/power/cpu_linux_backend.py`
- Test: `backend/tests/services/test_power_enforcement.py`

- [ ] **Step 1: Failing test für die Dev-Backend-Read-back-Methode**

Create `backend/tests/services/test_power_enforcement.py`:

```python
"""Tests for CPU cap enforcement (re-assert + drift detection)."""
import pytest

from app.schemas.power import PowerProfile, PowerProfileConfig
from app.services.power.cpu_dev_backend import DevCpuPowerBackend


@pytest.mark.asyncio
async def test_dev_backend_reports_enforcement_state_after_apply():
    backend = DevCpuPowerBackend()
    config = PowerProfileConfig(
        profile=PowerProfile.IDLE,
        governor="powersave",
        energy_performance_preference="power",
        min_freq_mhz=340,
        max_freq_mhz=400,
        description="test",
    )
    await backend.apply_profile(config)

    governor, max_mhz = await backend.read_enforcement_state()

    assert governor == "powersave"
    assert max_mhz == 400
```

- [ ] **Step 2: Test ausführen — muss fehlschlagen**

Run: `cd backend && python -m pytest tests/services/test_power_enforcement.py::test_dev_backend_reports_enforcement_state_after_apply -v`
Expected: FAIL — `AttributeError: 'DevCpuPowerBackend' object has no attribute 'read_enforcement_state'`

- [ ] **Step 3: Abstrakte Methode im Protocol ergänzen**

In `backend/app/services/power/cpu_protocol.py`, in der `CpuPowerBackend`-Klasse (neben `apply_profile`), ergänzen:

```python
    @abstractmethod
    async def read_enforcement_state(self) -> Tuple[Optional[str], Optional[int]]:
        """Read back (governor, scaling_max_mhz) for drift comparison.

        Returns (None, None) when the state cannot be read.
        """
        pass
```

Stelle sicher, dass `Optional` und `Tuple` aus `typing` importiert sind (sie sind es bereits in dieser Datei).

- [ ] **Step 4: Dev-Backend implementieren**

In `backend/app/services/power/cpu_dev_backend.py` — das Backend speichert in `apply_profile` bereits `self._current_governor`. Ergänze ein Feld für den max-Wert und die Read-back-Methode.

Im `__init__` (falls `_current_max_mhz` fehlt) ergänzen:
```python
        self._current_max_mhz: Optional[int] = None
```
In `apply_profile`, direkt nach `self._current_governor = config.governor`, ergänzen:
```python
        self._current_max_mhz = config.max_freq_mhz
```
Neue Methode am Klassenende:
```python
    async def read_enforcement_state(self) -> Tuple[Optional[str], Optional[int]]:
        """Return the last-applied governor and max frequency (simulated)."""
        return self._current_governor, self._current_max_mhz
```
Importe `Optional`, `Tuple` ergänzen, falls nicht vorhanden.

- [ ] **Step 5: Linux-Backend implementieren**

In `backend/app/services/power/cpu_linux_backend.py`, neue Methode (z. B. nach `get_current_governor`):
```python
    async def read_enforcement_state(self) -> Tuple[Optional[str], Optional[int]]:
        """Read cpu0 scaling_governor + scaling_max_freq for drift comparison."""
        cpu0 = self.CPUFREQ_PATH / "cpu0" / "cpufreq"
        governor = await self._read_sysfs(cpu0 / "scaling_governor")
        max_str = await self._read_sysfs(cpu0 / "scaling_max_freq")
        max_mhz = int(max_str) // 1000 if max_str and max_str.isdigit() else None
        return governor, max_mhz
```

- [ ] **Step 6: Test ausführen — muss bestehen**

Run: `cd backend && python -m pytest tests/services/test_power_enforcement.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/power/cpu_protocol.py backend/app/services/power/cpu_dev_backend.py backend/app/services/power/cpu_linux_backend.py backend/tests/services/test_power_enforcement.py
git commit -m "feat(power): add read_enforcement_state() to CPU backends"
```

---

## Task 2: Soll-Config zentralisieren (400-Floor + Boost-Override)

**Files:**
- Modify: `backend/app/services/power/manager.py`
- Test: `backend/tests/services/test_power_enforcement.py`

- [ ] **Step 1: Failing tests für die Soll-Config-Helfer**

In `backend/tests/services/test_power_enforcement.py` ergänzen:

```python
from app.schemas.power import ServicePowerProperty
from app.services.power.manager import PowerManagerService


@pytest.mark.asyncio
async def test_desired_config_floors_hold_cap_at_400(monkeypatch):
    mgr = PowerManagerService()

    async def fake_preset_config(prop):
        # Simulate a preset whose IDLE clock is below the 400 floor
        return PowerProfileConfig(
            profile=PowerProfile.IDLE, governor="powersave",
            energy_performance_preference="power",
            min_freq_mhz=200, max_freq_mhz=300, description="low preset",
        )

    monkeypatch.setattr(mgr, "_get_profile_config_from_preset", fake_preset_config)

    config = await mgr._desired_config_for(PowerProfile.IDLE)

    assert config.max_freq_mhz == 400          # floored up
    assert config.min_freq_mhz == int(400 * 0.85)


@pytest.mark.asyncio
async def test_desired_config_applies_boost_override_on_surge(monkeypatch):
    mgr = PowerManagerService()
    mgr._boost_max_override = 3000

    async def fake_preset_config(prop):
        return PowerProfileConfig(
            profile=PowerProfile.SURGE, governor="performance",
            energy_performance_preference="performance",
            min_freq_mhz=3600, max_freq_mhz=None, description="surge",
        )

    monkeypatch.setattr(mgr, "_get_profile_config_from_preset", fake_preset_config)

    config = await mgr._desired_config_for(PowerProfile.SURGE)

    assert config.max_freq_mhz == 3000         # override applied
```

> Hinweis: `PowerManagerService` ist ein Singleton (`__new__`). Für die Tests reicht die Instanz; `monkeypatch.setattr` ersetzt Methoden/Felder pro Test. Setze `mgr._boost_max_override = None` ggf. am Testende zurück — siehe Step 4.

- [ ] **Step 2: Tests ausführen — müssen fehlschlagen**

Run: `cd backend && python -m pytest tests/services/test_power_enforcement.py -k desired_config -v`
Expected: FAIL — `AttributeError: ... has no attribute '_desired_config_for'`

- [ ] **Step 3: Feld + Helfer im Manager implementieren**

In `backend/app/services/power/manager.py`, im `__init__` (bei den anderen Feldern, z. B. nach `self._dynamic_mode_config = None`):
```python
        self._boost_max_override: Optional[int] = None  # per-rule SURGE cap (MHz); None = full boost
        self._last_drift: Optional[dict] = None          # {"at", "field", "expected", "found"}
        self._cap_unenforceable: bool = False
        self._enforcement_task: Optional[asyncio.Task] = None
        self._watcher_absent_ticks: int = 0
```

Neuer Helfer (z. B. direkt nach `_get_profile_config_from_preset`):
```python
    HOLD_FLOOR_MHZ = 400

    async def _desired_config_for(self, profile: PowerProfile) -> Optional[PowerProfileConfig]:
        """Build the config that *should* be enforced for ``profile``.

        - Hold profiles (idle/low/medium): cap floored to HOLD_FLOOR_MHZ.
        - SURGE: if a per-rule boost override is set, use it as scaling_max;
          otherwise keep full boost (max_freq_mhz=None).
        Falls back to the static default profile when no preset is active.
        """
        power_property = ServicePowerProperty(profile.value)
        config = await self._get_profile_config_from_preset(power_property)
        if config is None:
            config = self._profiles.get(profile)
            if config is None:
                return None

        if profile == PowerProfile.SURGE:
            max_freq = self._boost_max_override  # None = full boost
            min_freq = config.min_freq_mhz
        else:
            floored = max(config.max_freq_mhz or self.HOLD_FLOOR_MHZ, self.HOLD_FLOOR_MHZ)
            max_freq = floored
            min_freq = int(floored * 0.85)

        return PowerProfileConfig(
            profile=config.profile,
            governor=config.governor,
            energy_performance_preference=config.energy_performance_preference,
            min_freq_mhz=min_freq,
            max_freq_mhz=max_freq,
            description=config.description,
        )
```

- [ ] **Step 4: Tests ausführen — müssen bestehen**

Run: `cd backend && python -m pytest tests/services/test_power_enforcement.py -k desired_config -v`
Expected: PASS

> Falls der Singleton-State zwischen Tests leakt, ergänze in der Testdatei eine Fixture:
> ```python
> @pytest.fixture(autouse=True)
> def _reset_override():
>     mgr = PowerManagerService()
>     mgr._boost_max_override = None
>     yield
>     mgr._boost_max_override = None
> ```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/manager.py backend/tests/services/test_power_enforcement.py
git commit -m "feat(power): centralize desired config with 400MHz floor + boost override"
```

---

## Task 3: Enforcement (Re-Assert + Drift-Erkennung)

**Files:**
- Modify: `backend/app/services/power/manager.py`
- Test: `backend/tests/services/test_power_enforcement.py`

- [ ] **Step 1: Failing tests für `_enforce_current_profile`**

In `backend/tests/services/test_power_enforcement.py` ergänzen:

```python
class _DriftBackend(DevCpuPowerBackend):
    """Dev backend whose read-back can be forced to differ from desired."""
    def __init__(self, drift_governor=None, drift_max=None):
        super().__init__()
        self._drift_governor = drift_governor
        self._drift_max = drift_max
        self.apply_calls = []

    async def apply_profile(self, config):
        self.apply_calls.append(config)
        return await super().apply_profile(config)

    async def read_enforcement_state(self):
        if self._drift_governor is not None or self._drift_max is not None:
            return self._drift_governor, self._drift_max
        return await super().read_enforcement_state()


@pytest.mark.asyncio
async def test_enforce_rewrites_on_drift(monkeypatch):
    mgr = PowerManagerService()
    mgr._current_profile = PowerProfile.IDLE
    backend = _DriftBackend(drift_governor="performance", drift_max=4668)
    mgr._backend = backend

    async def desired(profile):
        return PowerProfileConfig(
            profile=PowerProfile.IDLE, governor="powersave",
            energy_performance_preference="power",
            min_freq_mhz=340, max_freq_mhz=400, description="hold",
        )
    monkeypatch.setattr(mgr, "_desired_config_for", desired)

    await mgr._enforce_current_profile()

    assert len(backend.apply_calls) == 1                 # re-asserted
    assert mgr._last_drift is not None
    assert mgr._last_drift["found"] == "performance/4668"


@pytest.mark.asyncio
async def test_enforce_noop_when_in_sync(monkeypatch):
    mgr = PowerManagerService()
    mgr._current_profile = PowerProfile.IDLE
    backend = _DriftBackend()                            # no drift
    mgr._backend = backend
    # Prime the backend so read-back matches desired
    await backend.apply_profile(PowerProfileConfig(
        profile=PowerProfile.IDLE, governor="powersave",
        energy_performance_preference="power",
        min_freq_mhz=340, max_freq_mhz=400, description="hold"))
    backend.apply_calls.clear()

    async def desired(profile):
        return PowerProfileConfig(
            profile=PowerProfile.IDLE, governor="powersave",
            energy_performance_preference="power",
            min_freq_mhz=340, max_freq_mhz=400, description="hold")
    monkeypatch.setattr(mgr, "_desired_config_for", desired)

    await mgr._enforce_current_profile()

    assert backend.apply_calls == []                     # no re-write
```

- [ ] **Step 2: Tests ausführen — müssen fehlschlagen**

Run: `cd backend && python -m pytest tests/services/test_power_enforcement.py -k enforce -v`
Expected: FAIL — `AttributeError: ... '_enforce_current_profile'`

- [ ] **Step 3: `_enforce_current_profile` implementieren**

In `backend/app/services/power/manager.py` (z. B. nach `_apply_profile_internal`):

```python
    async def _enforce_current_profile(self) -> None:
        """Re-assert the desired hardware state; correct + log external drift.

        Runs every enforcement tick (primary only). Does NOT change the logical
        profile or write profile-change history — it only keeps the hardware
        aligned with what the current profile demands.
        """
        if self._backend is None or self._dynamic_mode_enabled:
            return

        desired = await self._desired_config_for(self._current_profile)
        if desired is None:
            return

        found_gov, found_max = await self._backend.read_enforcement_state()
        gov_drift = found_gov is not None and found_gov != desired.governor
        # desired.max None means "full boost" -> never counts as drift on the max axis
        max_drift = (
            desired.max_freq_mhz is not None
            and found_max is not None
            and found_max != desired.max_freq_mhz
        )

        if not gov_drift and not max_drift:
            self._cap_unenforceable = False
            return

        self._last_drift = {
            "at": datetime.now(timezone.utc).isoformat(),
            "field": "governor" if gov_drift else "max_freq",
            "expected": f"{desired.governor}/{desired.max_freq_mhz}",
            "found": f"{found_gov}/{found_max}",
        }
        logger.warning(
            "CPU cap drift detected (external override?): expected %s/%s, found %s/%s — re-asserting",
            desired.governor, desired.max_freq_mhz, found_gov, found_max,
        )

        success, _ = await self._backend.apply_profile(desired)

        # Verify it stuck; if not, flag as unenforceable (kernel clamp) and stop hammering.
        if success:
            vg, vm = await self._backend.read_enforcement_state()
            still_off = (vg is not None and vg != desired.governor) or (
                desired.max_freq_mhz is not None and vm is not None and vm != desired.max_freq_mhz
            )
            self._cap_unenforceable = bool(still_off)
            if still_off:
                logger.warning("CPU cap still not enforced after re-write (kernel clamp?)")
```

- [ ] **Step 4: Tests ausführen — müssen bestehen**

Run: `cd backend && python -m pytest tests/services/test_power_enforcement.py -k enforce -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/manager.py backend/tests/services/test_power_enforcement.py
git commit -m "feat(power): enforce current profile with drift detection + re-assert"
```

---

## Task 4: 2-s-Enforcement-Loop verdrahten

**Files:**
- Modify: `backend/app/services/power/manager.py`
- Test: `backend/tests/services/test_power_enforcement.py`

- [ ] **Step 1: Failing test — Loop ruft Enforcement, nur wenn Feature aktiv**

In `backend/tests/services/test_power_enforcement.py` ergänzen:

```python
import asyncio


@pytest.mark.asyncio
async def test_enforcement_loop_calls_enforce_when_enabled(monkeypatch):
    mgr = PowerManagerService()
    mgr._is_running = True
    mgr._primary = True
    calls = {"n": 0}

    async def fake_enforce():
        calls["n"] += 1
        if calls["n"] >= 2:
            mgr._is_running = False  # stop after two ticks

    monkeypatch.setattr(mgr, "_enforce_current_profile", fake_enforce)
    monkeypatch.setattr(mgr, "_run_process_watcher", lambda: None)
    monkeypatch.setattr(mgr, "_authority_active", lambda: True)
    # Make the loop tick instantly instead of sleeping 2s
    async def no_sleep(_):
        return None
    monkeypatch.setattr("app.services.power.manager.asyncio.sleep", no_sleep)

    await mgr._enforcement_loop()

    assert calls["n"] >= 2
```

- [ ] **Step 2: Test ausführen — muss fehlschlagen**

Run: `cd backend && python -m pytest tests/services/test_power_enforcement.py -k enforcement_loop -v`
Expected: FAIL — `AttributeError: ... '_enforcement_loop'`

- [ ] **Step 3: Loop + Gate + Task-Start/Stop implementieren**

In `backend/app/services/power/manager.py`:

`_authority_active` Helfer (liest die Feature-Config; bis Task 5 existiert, defensiv über config_store):
```python
    def _authority_active(self) -> bool:
        """True when BaluHost should enforce the cap (external authority enabled)."""
        try:
            from app.services.power.config_store import load_authority_config
            return bool(load_authority_config().get("external_authority_enabled"))
        except Exception:
            return False
```

Der Loop:
```python
    async def _enforcement_loop(self) -> None:
        """2-second primary-only loop: enforce cap + watch for boost processes."""
        while self._is_running:
            try:
                if self._primary and self._authority_active():
                    self._run_process_watcher()
                    await self._enforce_current_profile()
            except Exception as e:
                logger.error(f"Error in enforcement loop: {e}")
            await asyncio.sleep(2)
```

Platzhalter, bis Task 6 ihn ersetzt:
```python
    def _run_process_watcher(self) -> None:
        """Filled in by the process-watcher task. No-op until then."""
        return None
```

Task im `start()`-Pfad (dort wo `_monitor_task` erzeugt wird, z. B. direkt nach `self._monitor_task = asyncio.create_task(self._monitor_loop())`):
```python
        self._enforcement_task = asyncio.create_task(self._enforcement_loop())
```

In `stop()` (analog zur `_monitor_task`-Behandlung) ergänzen:
```python
        if self._enforcement_task:
            self._enforcement_task.cancel()
            try:
                await self._enforcement_task
            except asyncio.CancelledError:
                pass
            self._enforcement_task = None
```

- [ ] **Step 4: Test ausführen — muss bestehen**

Run: `cd backend && python -m pytest tests/services/test_power_enforcement.py -k enforcement_loop -v`
Expected: PASS

- [ ] **Step 5: Gesamte Enforcement-Datei grün**

Run: `cd backend && python -m pytest tests/services/test_power_enforcement.py -v`
Expected: PASS (alle)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/manager.py backend/tests/services/test_power_enforcement.py
git commit -m "feat(power): wire 2s enforcement loop (primary, authority-gated)"
```

---

# Phase 2 — PPD-Ownership

## Task 5: Authority-Config + `ppd_authority`-Service + Endpoint

**Files:**
- Create: `backend/app/services/power/ppd_authority.py`
- Modify: `backend/app/services/power/config_store.py`
- Modify: `backend/app/models/power.py`
- Modify: `backend/app/schemas/power.py`
- Modify: `backend/app/api/routes/power.py`
- Create: `backend/alembic/versions/<rev>_add_power_authority_config.py`
- Test: `backend/tests/services/test_ppd_authority.py`, `backend/tests/api/test_power_authority_routes.py`

- [ ] **Step 1: Singleton-Config-Tabelle modellieren**

In `backend/app/models/power.py` neue Klasse (Muster wie `PowerAutoScalingConfig`):
```python
class PowerAuthorityConfig(Base):
    """Singleton (id=1) config for CPU power authority + boost watcher."""

    __tablename__ = "power_authority_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_authority_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    boost_rules_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ppd_prev_active: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ppd_prev_enabled: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```
`PowerAuthorityConfig` ist über `from app.models.power import ...` erreichbar; `models/__init__.py` re-exportiert das Modul bereits — prüfe, ob `power`-Modelle dort gelistet sind, und ergänze `PowerAuthorityConfig` analog zu den vorhandenen Power-Modellen.

- [ ] **Step 2: Migration erstellen + Seed**

Run: `cd backend && alembic revision --autogenerate -m "add power_authority_config"`
Öffne die erzeugte Datei und stelle sicher, dass `upgrade()` die Tabelle anlegt **und** die Singleton-Zeile seedet:
```python
    op.create_table(
        "power_authority_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_authority_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("boost_rules_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ppd_prev_active", sa.Boolean(), nullable=True),
        sa.Column("ppd_prev_enabled", sa.Boolean(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("INSERT INTO power_authority_config (id, external_authority_enabled, boost_rules_enabled) VALUES (1, false, true)")
```
`downgrade()`: `op.drop_table("power_authority_config")`.

Run: `cd backend && alembic upgrade head`
Expected: ohne Fehler.

- [ ] **Step 3: config_store-Helfer (failing test first)**

In `backend/tests/services/test_ppd_authority.py`:
```python
"""Tests for PPD authority service + authority config."""
import pytest

from app.services.power import config_store


def test_authority_config_roundtrip():
    config_store.save_authority_config({"external_authority_enabled": True, "boost_rules_enabled": False})
    cfg = config_store.load_authority_config()
    assert cfg["external_authority_enabled"] is True
    assert cfg["boost_rules_enabled"] is False
    # reset
    config_store.save_authority_config({"external_authority_enabled": False, "boost_rules_enabled": True})
```

Run: `cd backend && python -m pytest tests/services/test_ppd_authority.py::test_authority_config_roundtrip -v`
Expected: FAIL — `AttributeError: module 'config_store' has no attribute 'load_authority_config'`

- [ ] **Step 4: config_store-Helfer implementieren**

In `backend/app/services/power/config_store.py` ergänzen (Muster wie `load_runtime_state`/`update_runtime_state`):
```python
def load_authority_config() -> dict[str, Any]:
    from app.models.power import PowerAuthorityConfig
    defaults = {"external_authority_enabled": False, "boost_rules_enabled": True,
                "ppd_prev_active": None, "ppd_prev_enabled": None}
    try:
        db = SessionLocal()
        try:
            row = db.query(PowerAuthorityConfig).filter(PowerAuthorityConfig.id == 1).first()
            if row is None:
                return defaults
            return {
                "external_authority_enabled": bool(row.external_authority_enabled),
                "boost_rules_enabled": bool(row.boost_rules_enabled),
                "ppd_prev_active": row.ppd_prev_active,
                "ppd_prev_enabled": row.ppd_prev_enabled,
            }
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to load authority config: {exc}")
        return defaults


def save_authority_config(fields: dict[str, Any]) -> bool:
    from app.models.power import PowerAuthorityConfig
    try:
        db = SessionLocal()
        try:
            row = db.query(PowerAuthorityConfig).filter(PowerAuthorityConfig.id == 1).first()
            if row is None:
                row = PowerAuthorityConfig(id=1)
                db.add(row)
            for key, value in fields.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            logger.warning(f"Failed to save authority config: {exc}")
            return False
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to open session for authority config: {exc}")
        return False
```

Run: `cd backend && python -m pytest tests/services/test_ppd_authority.py::test_authority_config_roundtrip -v`
Expected: PASS

- [ ] **Step 5: PPD-Service (failing test)**

In `backend/tests/services/test_ppd_authority.py` ergänzen:
```python
from app.services.power import ppd_authority


@pytest.mark.asyncio
async def test_acquire_stops_and_masks_ppd(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        class R:
            returncode = 0
            stdout = b"active\n" if args[:2] == ["systemctl", "is-active"] else b""
        return R()

    monkeypatch.setattr(ppd_authority.subprocess, "run", fake_run)

    await ppd_authority.acquire()

    assert ["sudo", "-n", "systemctl", "stop", "power-profiles-daemon"] in calls
    assert ["sudo", "-n", "systemctl", "mask", "power-profiles-daemon"] in calls


@pytest.mark.asyncio
async def test_release_unmasks_ppd(monkeypatch):
    calls = []
    monkeypatch.setattr(ppd_authority.subprocess, "run",
                        lambda args, **kw: calls.append(args) or type("R", (), {"returncode": 0, "stdout": b""})())
    await ppd_authority.release()
    assert ["sudo", "-n", "systemctl", "unmask", "power-profiles-daemon"] in calls
```

Run: `cd backend && python -m pytest tests/services/test_ppd_authority.py -k "acquire or release" -v`
Expected: FAIL — `ModuleNotFoundError`/`AttributeError`

- [ ] **Step 6: `ppd_authority.py` implementieren**

Create `backend/app/services/power/ppd_authority.py`:
```python
"""Stand power-profiles-daemon down so BaluHost is the sole CPU authority.

All subprocess calls use explicit argument lists (no shell=True). The
matching scoped sudoers rules are provisioned in deploy/install/templates/.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Optional

from app.services.power import config_store

logger = logging.getLogger(__name__)

UNIT = "power-profiles-daemon"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=10)


def _systemctl_state(verb: str) -> bool:
    """Return True if `systemctl <verb> UNIT` reports the positive state."""
    try:
        res = _run(["systemctl", verb, UNIT])
        out = (res.stdout or b"").decode(errors="ignore").strip()
        return out.startswith("active") or out.startswith("enabled")
    except Exception:
        return False


async def acquire() -> bool:
    """Record PPD's prior state, then stop + mask it. Returns True on success."""
    def _do() -> bool:
        prev_active = _systemctl_state("is-active")
        prev_enabled = _systemctl_state("is-enabled")
        config_store.save_authority_config(
            {"ppd_prev_active": prev_active, "ppd_prev_enabled": prev_enabled}
        )
        ok = True
        for verb in ("stop", "mask"):
            res = _run(["sudo", "-n", "systemctl", verb, UNIT])
            if res.returncode != 0:
                ok = False
                logger.warning("PPD %s failed (rc=%s): %s", verb, res.returncode,
                               (res.stderr or b"").decode(errors="ignore").strip())
        return ok
    return await asyncio.get_event_loop().run_in_executor(None, _do)


async def release() -> bool:
    """Unmask PPD and restore its prior active state."""
    def _do() -> bool:
        cfg = config_store.load_authority_config()
        ok = True
        res = _run(["sudo", "-n", "systemctl", "unmask", UNIT])
        if res.returncode != 0:
            ok = False
        if cfg.get("ppd_prev_active"):
            res = _run(["sudo", "-n", "systemctl", "start", UNIT])
            if res.returncode != 0:
                ok = False
        return ok
    return await asyncio.get_event_loop().run_in_executor(None, _do)


def status() -> dict:
    """Current PPD mask/active state for diagnostics/UI."""
    return {
        "ppd_active": _systemctl_state("is-active"),
        "ppd_masked": not _systemctl_state("is-enabled") and _is_masked(),
    }


def _is_masked() -> bool:
    try:
        res = _run(["systemctl", "is-enabled", UNIT])
        return (res.stdout or b"").decode(errors="ignore").strip() == "masked"
    except Exception:
        return False
```

Run: `cd backend && python -m pytest tests/services/test_ppd_authority.py -v`
Expected: PASS

- [ ] **Step 7: Schemas für Authority-Endpoint**

In `backend/app/schemas/power.py` ergänzen (bei den anderen Response-Modellen):
```python
class AuthorityStatusResponse(BaseModel):
    external_authority_enabled: bool
    boost_rules_enabled: bool
    ppd_active: bool
    ppd_masked: bool
    cap_unenforceable: bool
    last_drift: Optional[dict] = None


class AuthorityUpdateRequest(BaseModel):
    external_authority_enabled: Optional[bool] = None
    boost_rules_enabled: Optional[bool] = None
```
Stelle sicher, dass `BaseModel`, `Optional` importiert sind (sind sie in dieser Datei).

- [ ] **Step 8: Endpoints (failing test first)**

In `backend/tests/api/test_power_authority_routes.py`:
```python
"""Tests for /api/power authority endpoints (local-channel gated)."""
import pytest


def test_put_authority_requires_local_channel(remote_client, admin_headers):
    r = remote_client.put("/api/power/authority",
                          json={"external_authority_enabled": True},
                          headers=admin_headers)
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "local_channel_required"


def test_get_authority_status_ok(client, admin_headers):
    r = client.get("/api/power/authority", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "external_authority_enabled" in body
    assert "ppd_active" in body
```
> `client` (channel=local default), `remote_client`, `admin_headers` stammen aus `backend/tests/conftest.py` (siehe Tauri-Local-Admin-Arbeit).

Run: `cd backend && python -m pytest tests/api/test_power_authority_routes.py -v`
Expected: FAIL — 404 (Endpoints fehlen).

- [ ] **Step 9: Endpoints implementieren**

In `backend/app/api/routes/power.py`:
- Importe ergänzen: `from app.schemas.power import AuthorityStatusResponse, AuthorityUpdateRequest`, `from app.services.power import ppd_authority, config_store`.
```python
@router.get("/authority", response_model=AuthorityStatusResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_authority_status(
    request: Request, response: Response,
    _: UserPublic = Depends(deps.get_current_admin),
) -> AuthorityStatusResponse:
    cfg = config_store.load_authority_config()
    ppd = ppd_authority.status()
    mgr = get_power_manager()
    return AuthorityStatusResponse(
        external_authority_enabled=cfg["external_authority_enabled"],
        boost_rules_enabled=cfg["boost_rules_enabled"],
        ppd_active=ppd["ppd_active"],
        ppd_masked=ppd["ppd_masked"],
        cap_unenforceable=getattr(mgr, "_cap_unenforceable", False),
        last_drift=getattr(mgr, "_last_drift", None),
    )


@router.put("/authority", response_model=AuthorityStatusResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_authority(
    request: Request, response: Response,
    body: AuthorityUpdateRequest,
    user: UserPublic = Depends(deps.require_local_admin),
) -> AuthorityStatusResponse:
    cfg = config_store.load_authority_config()
    if body.external_authority_enabled is not None and \
            body.external_authority_enabled != cfg["external_authority_enabled"]:
        if body.external_authority_enabled:
            await ppd_authority.acquire()
        else:
            await ppd_authority.release()
        config_store.save_authority_config(
            {"external_authority_enabled": body.external_authority_enabled})
    if body.boost_rules_enabled is not None:
        config_store.save_authority_config({"boost_rules_enabled": body.boost_rules_enabled})

    from app.services.audit import get_audit_logger_db
    get_audit_logger_db().log_security_event(
        action="power_authority_update", user=user.username,
        details={"external_authority_enabled": body.external_authority_enabled,
                 "boost_rules_enabled": body.boost_rules_enabled},
        success=True,
    )
    return await get_authority_status(request, response, user)  # type: ignore[arg-type]
```
> Prüfe den exakten Import/Aufruf von `get_audit_logger_db` an einem bestehenden Route-File (z. B. `auth.py`) und passe an, falls die Signatur ein `db`-Argument erwartet.

Run: `cd backend && python -m pytest tests/api/test_power_authority_routes.py -v`
Expected: PASS

- [ ] **Step 10: Manager wendet Authority an/ab beim Toggle**

Damit der Cap nach dem Einschalten sofort statt erst beim nächsten Profilwechsel greift, beim Aktivieren ein Enforce auslösen. In `update_authority`, im `if body.external_authority_enabled:`-Zweig nach `acquire()`:
```python
            try:
                await get_power_manager()._enforce_current_profile()
            except Exception:
                pass
```

Run: `cd backend && python -m pytest tests/api/test_power_authority_routes.py tests/services/test_ppd_authority.py -v`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/power/ppd_authority.py backend/app/services/power/config_store.py backend/app/models/power.py backend/app/models/__init__.py backend/app/schemas/power.py backend/app/api/routes/power.py backend/alembic/versions backend/tests/services/test_ppd_authority.py backend/tests/api/test_power_authority_routes.py
git commit -m "feat(power): PPD authority service + local-only authority endpoints"
```

---

# Phase 3 — Allowlist + Game-Session-Watcher

## Task 6: `power_boost_rules`-Modell + Migration + Seed

**Files:**
- Create: `backend/app/models/power_boost_rule.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_add_power_boost_rules.py`
- Test: `backend/tests/services/test_process_watcher.py`

- [ ] **Step 1: Modell**

Create `backend/app/models/power_boost_rule.py`:
```python
"""CPU boost allowlist rules — presence lifts the enforced cap."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class PowerBoostRule(Base):
    __tablename__ = "power_boost_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # process_glob | game_session
    pattern: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    target_max_mhz: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = full boost
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<PowerBoostRule(id={self.id}, kind='{self.kind}', label='{self.label}')>"
```
In `backend/app/models/__init__.py`: Import + `__all__`-Eintrag `PowerBoostRule` ergänzen (Muster der anderen Modelle).

- [ ] **Step 2: Migration + Seed der game_session-Regel**

Run: `cd backend && alembic revision --autogenerate -m "add power_boost_rules"`
Im `upgrade()` zusätzlich die eingebaute Regel seeden:
```python
    op.execute(
        "INSERT INTO power_boost_rules (kind, pattern, label, target_max_mhz, enabled) "
        "VALUES ('game_session', NULL, 'Steam/Proton-Spielsitzung', NULL, true)"
    )
```
`downgrade()`: `op.drop_table("power_boost_rules")`.

Run: `cd backend && alembic upgrade head`
Expected: ohne Fehler.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/power_boost_rule.py backend/app/models/__init__.py backend/alembic/versions
git commit -m "feat(power): power_boost_rules model + migration + seeded game-session rule"
```

---

## Task 7: Game-Session-/Glob-Erkennung (reine Logik)

**Files:**
- Create: `backend/app/services/power/process_watcher.py`
- Test: `backend/tests/services/test_process_watcher.py`

Die Erkennung wird als **reine Funktion** über eine Liste von „Prozess-Sichten" gebaut, damit sie ohne echtes psutil testbar ist. Ein dünner psutil-Adapter (Task 8) liefert diese Liste zur Laufzeit.

- [ ] **Step 1: Failing tests**

Create `backend/tests/services/test_process_watcher.py`:
```python
"""Tests for boost-rule process matching."""
from app.services.power.process_watcher import ProcInfo, match_boost_rules


WRAPPER = ProcInfo(name="pressure-vessel", cmdline="pressure-vessel-wrap -- game")
REAPER = ProcInfo(name="reaper", cmdline="reaper SteamLaunch AppId=1245620 -- game")
STEAM_IDLE = ProcInfo(name="steam", cmdline="/home/sven/.steam/steam")
FIREFOX = ProcInfo(name="firefox", cmdline="/usr/lib/firefox/firefox")


def _rule(kind, pattern=None, target=None, enabled=True, label="x"):
    return {"kind": kind, "pattern": pattern, "target_max_mhz": target,
            "enabled": enabled, "label": label}


def test_steam_in_tray_does_not_match_game_session():
    rules = [_rule("game_session")]
    hit, target = match_boost_rules([STEAM_IDLE, FIREFOX], rules)
    assert hit is False
    assert target is None


def test_pressure_vessel_matches_game_session():
    rules = [_rule("game_session")]
    hit, target = match_boost_rules([STEAM_IDLE, WRAPPER], rules)
    assert hit is True
    assert target is None          # full boost (rule target None)


def test_reaper_steamlaunch_matches_game_session():
    rules = [_rule("game_session")]
    hit, _ = match_boost_rules([REAPER], rules)
    assert hit is True


def test_process_glob_matches_and_carries_target():
    rules = [_rule("process_glob", pattern="lutris*", target=3000)]
    procs = [ProcInfo(name="lutris-wrapper", cmdline="lutris ...")]
    hit, target = match_boost_rules(procs, rules)
    assert hit is True
    assert target == 3000


def test_highest_target_wins_none_beats_all():
    rules = [_rule("process_glob", pattern="lutris*", target=3000),
             _rule("game_session")]  # game_session target None = full boost
    procs = [ProcInfo(name="lutris", cmdline="lutris"), WRAPPER]
    hit, target = match_boost_rules(procs, rules)
    assert hit is True
    assert target is None          # None (full) beats the 3000 cap


def test_disabled_rule_ignored():
    rules = [_rule("game_session", enabled=False)]
    hit, _ = match_boost_rules([WRAPPER], rules)
    assert hit is False
```

Run: `cd backend && python -m pytest tests/services/test_process_watcher.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.power.process_watcher`

- [ ] **Step 2: Implementieren**

Create `backend/app/services/power/process_watcher.py`:
```python
"""Detect boost-eligible processes for the CPU power authority.

`match_boost_rules` is pure (testable without psutil). A psutil adapter
(`snapshot_processes`) feeds it live data from the enforcement loop.
"""
from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Wrapper processes that exist ONLY during an active Steam/Proton/Wine game
# session (not when Steam merely idles in the tray).
GAME_WRAPPERS = (
    "pressure-vessel", "pv-bwrap", "proton",
    "wine", "wine64", "wineserver", "wine64-preloader",
)


@dataclass
class ProcInfo:
    name: str
    cmdline: str = ""


def _is_game_session(procs: List[ProcInfo]) -> bool:
    for p in procs:
        name = (p.name or "").lower()
        if name in GAME_WRAPPERS or name.startswith("wine"):
            return True
        # `reaper` is generic; only count it for an actual SteamLaunch
        if name == "reaper" and "steamlaunch" in (p.cmdline or "").lower():
            return True
    return False


def _glob_match(procs: List[ProcInfo], pattern: str) -> bool:
    pat = (pattern or "").lower()
    for p in procs:
        name = (p.name or "").lower()
        # exact/glob, plus 15-char comm truncation -> prefix tolerance
        if fnmatch.fnmatch(name, pat) or (len(name) == 15 and pat.startswith(name)):
            return True
    return False


def match_boost_rules(
    procs: List[ProcInfo], rules: List[dict]
) -> Tuple[bool, Optional[int]]:
    """Return (any_hit, effective_target_mhz).

    effective_target_mhz = highest target among matched rules; ``None`` means
    full boost and beats any finite cap.
    """
    matched_targets: List[Optional[int]] = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        kind = rule.get("kind")
        hit = False
        if kind == "game_session":
            hit = _is_game_session(procs)
        elif kind == "process_glob" and rule.get("pattern"):
            hit = _glob_match(procs, rule["pattern"])
        if hit:
            matched_targets.append(rule.get("target_max_mhz"))

    if not matched_targets:
        return False, None
    if any(t is None for t in matched_targets):
        return True, None  # full boost wins
    return True, max(matched_targets)  # type: ignore[type-var]
```

Run: `cd backend && python -m pytest tests/services/test_process_watcher.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/power/process_watcher.py backend/tests/services/test_process_watcher.py
git commit -m "feat(power): pure boost-rule process matching (game-session + glob)"
```

---

## Task 8: psutil-Adapter + Watcher-Anbindung (Hysterese + Demand)

**Files:**
- Modify: `backend/app/services/power/process_watcher.py`
- Modify: `backend/app/services/power/manager.py`
- Test: `backend/tests/services/test_process_watcher.py`

- [ ] **Step 1: Failing test für die Hysterese im Manager**

In `backend/tests/services/test_process_watcher.py` ergänzen:
```python
import pytest
from app.schemas.power import PowerProfile
from app.services.power.manager import PowerManagerService


@pytest.mark.asyncio
async def test_watcher_registers_then_releases_after_two_absent_ticks(monkeypatch):
    mgr = PowerManagerService()
    mgr._primary = True
    mgr._watcher_absent_ticks = 0
    mgr._boost_max_override = None
    events = []

    async def fake_register(source, level, **kw):
        events.append(("register", level, kw.get("max_freq_override")))
        return source
    async def fake_unregister(source):
        events.append(("unregister", source))
        return True
    monkeypatch.setattr(mgr, "register_demand", fake_register)
    monkeypatch.setattr(mgr, "unregister_demand", fake_unregister)
    monkeypatch.setattr(mgr, "_active_boost_rules", lambda: [{"kind": "game_session", "enabled": True, "pattern": None, "target_max_mhz": None}])

    # Tick 1: game present -> register
    monkeypatch.setattr("app.services.power.process_watcher.snapshot_processes",
                        lambda: [__import__("app.services.power.process_watcher", fromlist=["ProcInfo"]).ProcInfo(name="pressure-vessel")])
    await mgr._watch_tick()
    assert events[0][0] == "register"
    assert mgr._game_demand_active is True

    # Game gone — tick 2 (1 absent) -> still active (hysteresis)
    monkeypatch.setattr("app.services.power.process_watcher.snapshot_processes", lambda: [])
    await mgr._watch_tick()
    assert mgr._game_demand_active is True

    # tick 3 (2 absent) -> release
    await mgr._watch_tick()
    assert ("unregister", "game-session") in events
    assert mgr._game_demand_active is False
```

Run: `cd backend && python -m pytest tests/services/test_process_watcher.py -k watcher_registers -v`
Expected: FAIL — fehlende `snapshot_processes` / `_watch_tick` / `_active_boost_rules`.

- [ ] **Step 2: psutil-Adapter ergänzen**

In `backend/app/services/power/process_watcher.py` ergänzen:
```python
def snapshot_processes() -> List[ProcInfo]:
    """Live process list via psutil (name + cmdline). Best-effort."""
    import psutil
    out: List[ProcInfo] = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            info = proc.info
            name = info.get("name") or ""
            cmd = " ".join(info.get("cmdline") or [])
            out.append(ProcInfo(name=name, cmdline=cmd))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out
```

- [ ] **Step 3: Manager-Anbindung implementieren**

In `backend/app/services/power/manager.py`, im `__init__` ergänzen:
```python
        self._game_demand_active: bool = False
```
Helfer für aktive Regeln:
```python
    def _active_boost_rules(self) -> list[dict]:
        from app.services.power.config_store import load_authority_config, list_boost_rules
        if not load_authority_config().get("boost_rules_enabled", True):
            return []
        return list_boost_rules(enabled_only=True)
```
Der Watch-Tick (mit Hysterese, 2 Absent-Ticks):
```python
    async def _watch_tick(self) -> None:
        from app.services.power import process_watcher
        rules = self._active_boost_rules()
        if not rules:
            if self._game_demand_active:
                await self.unregister_demand("game-session")
                self._game_demand_active = False
                self._boost_max_override = None
            return

        procs = process_watcher.snapshot_processes()
        hit, target = process_watcher.match_boost_rules(procs, rules)

        if hit:
            self._watcher_absent_ticks = 0
            if not self._game_demand_active or self._boost_max_override != target:
                self._boost_max_override = target
                await self.register_demand(
                    "game-session", PowerProfile.SURGE,
                    max_freq_override=target, description="Boost-Allowlist",
                )
                self._game_demand_active = True
        elif self._game_demand_active:
            self._watcher_absent_ticks += 1
            if self._watcher_absent_ticks >= 2:
                await self.unregister_demand("game-session")
                self._game_demand_active = False
                self._boost_max_override = None
                self._watcher_absent_ticks = 0
```
Ersetze die Platzhalter-Methode `_run_process_watcher` aus Task 4 durch einen Aufruf des Ticks. Da `_enforcement_loop` async ist, ändere die Stelle im Loop von `self._run_process_watcher()` zu `await self._watch_tick()` und entferne `_run_process_watcher`.

> `register_demand` muss den neuen Parameter `max_freq_override` akzeptieren — siehe Step 4.

- [ ] **Step 4: `register_demand` um `max_freq_override` erweitern**

In `register_demand` die Signatur um `max_freq_override: Optional[int] = None` ergänzen und vor dem `_recalculate_profile`-Aufruf auf der primary-Seite setzen:
```python
        if max_freq_override is not None or level == PowerProfile.SURGE:
            self._boost_max_override = max_freq_override
```
So liest `_desired_config_for` beim SURGE-Apply den korrekten Cap. (Bei `unregister_demand("game-session")` wird `_boost_max_override` im Watch-Tick wieder auf None gesetzt.)

- [ ] **Step 5: `list_boost_rules` in config_store (kurz, hier mitnehmen)**

In `backend/app/services/power/config_store.py`:
```python
def list_boost_rules(enabled_only: bool = False) -> list[dict]:
    from app.models.power_boost_rule import PowerBoostRule
    try:
        db = SessionLocal()
        try:
            q = db.query(PowerBoostRule)
            if enabled_only:
                q = q.filter(PowerBoostRule.enabled == True)  # noqa: E712
            return [
                {"id": r.id, "kind": r.kind, "pattern": r.pattern, "label": r.label,
                 "target_max_mhz": r.target_max_mhz, "enabled": bool(r.enabled)}
                for r in q.order_by(PowerBoostRule.id).all()
            ]
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to list boost rules: {exc}")
        return []
```

- [ ] **Step 6: Tests ausführen — müssen bestehen**

Run: `cd backend && python -m pytest tests/services/test_process_watcher.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/power/process_watcher.py backend/app/services/power/manager.py backend/app/services/power/config_store.py backend/tests/services/test_process_watcher.py
git commit -m "feat(power): wire game-session watcher to demand system with hysteresis"
```

---

## Task 9: Boost-Rule-CRUD + „Boost jetzt" Endpoints (lokal-only)

**Files:**
- Modify: `backend/app/services/power/config_store.py`
- Modify: `backend/app/schemas/power.py`
- Modify: `backend/app/api/routes/power.py`
- Test: `backend/tests/api/test_power_authority_routes.py`

- [ ] **Step 1: CRUD-Helfer in config_store (failing test)**

In `backend/tests/api/test_power_authority_routes.py` ergänzen:
```python
def test_boost_rule_crud_local_only(client, remote_client, admin_headers):
    # remote create -> 403
    r = remote_client.post("/api/power/boost-rules",
                           json={"kind": "process_glob", "pattern": "lutris*", "label": "Lutris"},
                           headers=admin_headers)
    assert r.status_code == 403

    # local create -> 200
    r = client.post("/api/power/boost-rules",
                    json={"kind": "process_glob", "pattern": "lutris*", "label": "Lutris", "target_max_mhz": 3000},
                    headers=admin_headers)
    assert r.status_code == 200
    rule_id = r.json()["id"]

    # list contains it (admin, any channel)
    r = client.get("/api/power/boost-rules", headers=admin_headers)
    assert any(x["id"] == rule_id for x in r.json()["rules"])

    # delete local -> 200
    r = client.delete(f"/api/power/boost-rules/{rule_id}", headers=admin_headers)
    assert r.status_code == 200
```

Run: `cd backend && python -m pytest tests/api/test_power_authority_routes.py -k boost_rule -v`
Expected: FAIL — 404.

- [ ] **Step 2: config_store CRUD ergänzen**

```python
def create_boost_rule(kind: str, label: str, pattern: Optional[str],
                      target_max_mhz: Optional[int]) -> Optional[dict]:
    from app.models.power_boost_rule import PowerBoostRule
    db = SessionLocal()
    try:
        row = PowerBoostRule(kind=kind, label=label, pattern=pattern,
                             target_max_mhz=target_max_mhz, enabled=True)
        db.add(row); db.commit(); db.refresh(row)
        return {"id": row.id, "kind": row.kind, "pattern": row.pattern,
                "label": row.label, "target_max_mhz": row.target_max_mhz, "enabled": True}
    except Exception as exc:
        db.rollback(); logger.warning(f"create boost rule failed: {exc}"); return None
    finally:
        db.close()


def update_boost_rule(rule_id: int, fields: dict) -> bool:
    from app.models.power_boost_rule import PowerBoostRule
    db = SessionLocal()
    try:
        row = db.query(PowerBoostRule).filter(PowerBoostRule.id == rule_id).first()
        if row is None:
            return False
        for k, v in fields.items():
            if hasattr(row, k) and k in {"kind", "pattern", "label", "target_max_mhz", "enabled"}:
                setattr(row, k, v)
        db.commit(); return True
    except Exception as exc:
        db.rollback(); logger.warning(f"update boost rule failed: {exc}"); return False
    finally:
        db.close()


def delete_boost_rule(rule_id: int) -> bool:
    from app.models.power_boost_rule import PowerBoostRule
    db = SessionLocal()
    try:
        row = db.query(PowerBoostRule).filter(PowerBoostRule.id == rule_id).first()
        if row is None:
            return False
        db.delete(row); db.commit(); return True
    except Exception as exc:
        db.rollback(); logger.warning(f"delete boost rule failed: {exc}"); return False
    finally:
        db.close()
```

- [ ] **Step 3: Schemas**

In `backend/app/schemas/power.py`:
```python
class BoostRule(BaseModel):
    id: int
    kind: str
    pattern: Optional[str] = None
    label: str
    target_max_mhz: Optional[int] = None
    enabled: bool


class BoostRulesResponse(BaseModel):
    rules: list[BoostRule]


class BoostRuleCreateRequest(BaseModel):
    kind: str = Field(..., pattern="^(process_glob|game_session)$")
    label: str = Field(..., min_length=1, max_length=120)
    pattern: Optional[str] = Field(None, max_length=200)
    target_max_mhz: Optional[int] = Field(None, ge=400, le=6000)


class BoostRuleUpdateRequest(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=120)
    pattern: Optional[str] = Field(None, max_length=200)
    target_max_mhz: Optional[int] = Field(None, ge=400, le=6000)
    enabled: Optional[bool] = None


class BoostNowRequest(BaseModel):
    duration_seconds: int = Field(1800, ge=30, le=86400)
    target_max_mhz: Optional[int] = Field(None, ge=400, le=6000)
```
Stelle sicher, dass `Field` aus `pydantic` importiert ist.

- [ ] **Step 4: Endpoints**

In `backend/app/api/routes/power.py` (Importe der neuen Schemas ergänzen):
```python
@router.get("/boost-rules", response_model=BoostRulesResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def list_boost_rules_route(
    request: Request, response: Response,
    _: UserPublic = Depends(deps.get_current_admin),
) -> BoostRulesResponse:
    return BoostRulesResponse(rules=config_store.list_boost_rules())


@router.post("/boost-rules", response_model=BoostRule)
@user_limiter.limit(get_limit("admin_operations"))
async def create_boost_rule_route(
    request: Request, response: Response,
    body: BoostRuleCreateRequest,
    _: UserPublic = Depends(deps.require_local_admin),
) -> BoostRule:
    rule = config_store.create_boost_rule(body.kind, body.label, body.pattern, body.target_max_mhz)
    if rule is None:
        raise HTTPException(status_code=500, detail="Failed to create boost rule")
    return BoostRule(**rule)


@router.put("/boost-rules/{rule_id}", response_model=BoostRule)
@user_limiter.limit(get_limit("admin_operations"))
async def update_boost_rule_route(
    request: Request, response: Response, rule_id: int,
    body: BoostRuleUpdateRequest,
    _: UserPublic = Depends(deps.require_local_admin),
) -> BoostRule:
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not config_store.update_boost_rule(rule_id, fields):
        raise HTTPException(status_code=404, detail="Boost rule not found")
    rule = next((r for r in config_store.list_boost_rules() if r["id"] == rule_id), None)
    return BoostRule(**rule)  # type: ignore[arg-type]


@router.delete("/boost-rules/{rule_id}")
@user_limiter.limit(get_limit("admin_operations"))
async def delete_boost_rule_route(
    request: Request, response: Response, rule_id: int,
    _: UserPublic = Depends(deps.require_local_admin),
):
    if not config_store.delete_boost_rule(rule_id):
        raise HTTPException(status_code=404, detail="Boost rule not found")
    return {"success": True}


@router.post("/boost-now")
@user_limiter.limit(get_limit("admin_operations"))
async def boost_now_route(
    request: Request, response: Response,
    body: BoostNowRequest,
    _: UserPublic = Depends(deps.require_local_admin),
):
    mgr = get_power_manager()
    await mgr.register_demand(
        "manual-boost", PowerProfile.SURGE,
        max_freq_override=body.target_max_mhz,
        timeout_seconds=body.duration_seconds, description="Manueller Boost",
    )
    return {"success": True, "duration_seconds": body.duration_seconds}
```

Run: `cd backend && python -m pytest tests/api/test_power_authority_routes.py -v`
Expected: PASS

- [ ] **Step 5: Volle Power-Test-Suite grün**

Run: `cd backend && python -m pytest tests/services/test_power_enforcement.py tests/services/test_process_watcher.py tests/services/test_ppd_authority.py tests/api/test_power_authority_routes.py tests/services/test_power_manager.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/config_store.py backend/app/schemas/power.py backend/app/api/routes/power.py backend/tests/api/test_power_authority_routes.py
git commit -m "feat(power): boost-rule CRUD + boost-now endpoints (local-only)"
```

---

# Phase 4 — Deploy (sudoers)

## Task 10: Scoped sudoers für power-profiles-daemon

**Files:**
- Modify: `deploy/install/templates/<sudoers-template>` (exakten Namen beim Bearbeiten ermitteln, z. B. `baluhost-sudoers` / `*.sudoers`)
- Modify: `.claude/rules/ci-cd-security.md` (Inventar)

- [ ] **Step 1: Bestehende sudoers-Vorlage finden**

Run: `ls deploy/install/templates`
Identifiziere die Datei mit den cpufreq-`tee`-Regeln (das ist die richtige Stelle).

- [ ] **Step 2: Vier exakt gescopte Zeilen ergänzen**

In der sudoers-Vorlage (User `baluhost`), keine Globs:
```
baluhost ALL=(root) NOPASSWD: /usr/bin/systemctl stop power-profiles-daemon
baluhost ALL=(root) NOPASSWD: /usr/bin/systemctl start power-profiles-daemon
baluhost ALL=(root) NOPASSWD: /usr/bin/systemctl mask power-profiles-daemon
baluhost ALL=(root) NOPASSWD: /usr/bin/systemctl unmask power-profiles-daemon
```
> Prüfe den realen `systemctl`-Pfad auf Debian 13 (`command -v systemctl` → i. d. R. `/usr/bin/systemctl`). Passe den Pfad an, falls abweichend; sudoers verlangt absolute Pfade.

- [ ] **Step 3: Syntax validieren (lokal auf dem Server, manuell)**

Hinweis im Plan für den Operator: `sudo visudo -cf <gerendertes-file>` muss „parsed OK" melden.

- [ ] **Step 4: Security-Regeln-Inventar nachziehen**

In `.claude/rules/ci-cd-security.md` (Layer-1-/sudoers-Abschnitt) die neuen vier Zeilen als bekannte, gescopte Ausnahme dokumentieren.

- [ ] **Step 5: Commit**

```bash
git add deploy/install/templates .claude/rules/ci-cd-security.md
git commit -m "deploy(power): scoped sudoers for power-profiles-daemon mask/unmask"
```

---

# Phase 5 — Frontend

> Komponentenort während der Implementierung lokalisieren: die Energy-Ansicht unter
> *System Control → Hardware → Energy*. Bestehende Power-Komponenten liegen in
> `client/src/components/power/`. API-Client-Muster: `client/src/api/` + `client/src/lib/api.ts`.
> Local-only-Gating über den vorhandenen `useChannelStatus`-Hook.

## Task 11: Live-Frequenz + freq_range-Fix (Anzeige-Bug)

**Files:**
- Modify: `backend/app/services/power/manager.py` (`get_power_status`: `freq_range` aus aktivem Preset)
- Modify: betroffene Energy-Anzeige-Komponente in `client/src/components/power/`
- Test: `backend/tests/services/test_power_enforcement.py`

- [ ] **Step 1: Failing test — freq_range folgt aktivem Preset, nicht `_profiles`**

In `backend/tests/services/test_power_enforcement.py`:
```python
@pytest.mark.asyncio
async def test_status_freq_range_uses_desired_config(monkeypatch):
    mgr = PowerManagerService()
    mgr._current_profile = PowerProfile.IDLE
    mgr._backend = DevCpuPowerBackend()

    async def desired(profile):
        return PowerProfileConfig(
            profile=PowerProfile.IDLE, governor="powersave",
            energy_performance_preference="power",
            min_freq_mhz=510, max_freq_mhz=600, description="preset")
    monkeypatch.setattr(mgr, "_desired_config_for", desired)

    status = await mgr.get_power_status()
    assert status.frequency_range == "510-600 MHz"
```
> Prüfe den realen Feldnamen im `PowerStatusResponse` (`frequency_range` vs `freq_range`) in `schemas/power.py` und passe Test + Implementierung an.

Run: `cd backend && python -m pytest tests/services/test_power_enforcement.py -k freq_range -v`
Expected: FAIL.

- [ ] **Step 2: `get_power_status` umstellen**

In `manager.py`, die `freq_range`-Ableitung (aktuell aus `self._profiles.get(...)`) ersetzen durch die Soll-Config:
```python
        desired = await self._desired_config_for(self._current_profile)
        freq_range = None
        if desired and desired.min_freq_mhz and desired.max_freq_mhz:
            freq_range = f"{desired.min_freq_mhz}-{desired.max_freq_mhz} MHz"
        elif self._current_profile == PowerProfile.SURGE:
            freq_range = "Full boost"
```
Behalte den live gemessenen `freq` (`get_current_frequency_mhz`) wie bisher im Response.

Run: `cd backend && python -m pytest tests/services/test_power_enforcement.py -k freq_range -v`
Expected: PASS

- [ ] **Step 3: Frontend zeigt Live-Frequenz prominent**

In der Energy-Komponente die prominente Zahl auf die live gemessene Frequenz (`status.frequency_mhz` o. ä. — realen Feldnamen prüfen) umstellen, den Soll-Bereich (`frequency_range`) als sekundäre Zeile („Ziel: …") darunter. Bestehende i18n-Keys verwenden/ergänzen.

- [ ] **Step 4: Frontend-Build prüfen**

Run: `cd client && npm run build`
Expected: Build erfolgreich.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/manager.py backend/tests/services/test_power_enforcement.py client/src
git commit -m "fix(power): show live CPU freq + derive freq_range from active preset"
```

---

## Task 12: Authority-Schalter + Drift-Badge (UI)

**Files:**
- Modify: `client/src/api/` (Power-Client um `getAuthority`, `updateAuthority`)
- Create/Modify: Komponente `client/src/components/power/AuthorityPanel.tsx`
- Modify: i18n de/en

- [ ] **Step 1: API-Client**

Im Power-API-Modul ergänzen (Muster der bestehenden Calls):
```ts
export const getAuthority = () => api.get('/power/authority').then(r => r.data);
export const updateAuthority = (body: { external_authority_enabled?: boolean; boost_rules_enabled?: boolean }) =>
  api.put('/power/authority', body).then(r => r.data);
```

- [ ] **Step 2: AuthorityPanel-Komponente**

`AuthorityPanel.tsx`:
- Toggle „BaluHost steuert CPU allein (PPD stilllegen)" → `updateAuthority({ external_authority_enabled })`.
- Toggle ist **deaktiviert wenn `channelStatus.channel !== 'local'`** (`useChannelStatus`), mit Hinweistext „Nur aus der Companion-App am Server änderbar".
- Drift-Badge: wenn `authority.last_drift` gesetzt → gelbes Badge „Extern überschrieben — korrigiert" mit Tooltip (expected/found).
- `cap_unenforceable` → rotes Badge „Cap nicht durchsetzbar (Kernel/Treiber)".
Daten via React Query (`useQuery(['power-authority'], getAuthority)`), Invalidate nach Mutation.

- [ ] **Step 3: i18n-Keys** in `client/src/i18n/locales/de/*.json` und `en/*.json` ergänzen.

- [ ] **Step 4: Build**

Run: `cd client && npm run build`
Expected: erfolgreich.

- [ ] **Step 5: Commit**

```bash
git add client/src
git commit -m "feat(power): authority toggle + drift/unenforceable badges (local-only)"
```

---

## Task 13: Allowlist-Editor + „Boost jetzt" (UI)

**Files:**
- Modify: `client/src/api/` (boost-rules + boost-now)
- Create: `client/src/components/power/BoostRulesEditor.tsx`
- Modify: i18n de/en

- [ ] **Step 1: API-Client**

```ts
export const listBoostRules = () => api.get('/power/boost-rules').then(r => r.data.rules);
export const createBoostRule = (b: { kind: string; label: string; pattern?: string|null; target_max_mhz?: number|null }) =>
  api.post('/power/boost-rules', b).then(r => r.data);
export const updateBoostRule = (id: number, b: object) => api.put(`/power/boost-rules/${id}`, b).then(r => r.data);
export const deleteBoostRule = (id: number) => api.delete(`/power/boost-rules/${id}`).then(r => r.data);
export const boostNow = (b: { duration_seconds: number; target_max_mhz?: number|null }) =>
  api.post('/power/boost-now', b).then(r => r.data);
```

- [ ] **Step 2: BoostRulesEditor-Komponente**

- Liste der Regeln (Label, kind, pattern, Ziel-MHz, enabled-Toggle).
- „Regel hinzufügen": kind = `process_glob` (Pattern-Feld) | `game_session`; optionales Ziel-MHz (leer = voller Boost).
- Lösch-Button pro Regel (nicht für die `game_session`-System-Regel anbieten, falls gewünscht — optional).
- Alle mutierenden Aktionen **deaktiviert wenn `channel !== 'local'`** + Companion-Hinweis.
- „Boost jetzt"-Block: Dauer-Auswahl (30 min default) + optional Ziel-MHz → `boostNow(...)`.
- React Query mit Invalidate nach jeder Mutation.

- [ ] **Step 3: i18n-Keys** ergänzen.

- [ ] **Step 4: Build + (optional) Smoketest**

Run: `cd client && npm run build`
Expected: erfolgreich.

- [ ] **Step 5: Commit**

```bash
git add client/src
git commit -m "feat(power): allowlist editor + boost-now control (local-only)"
```

---

## Task 14: Integration & Abschluss

- [ ] **Step 1: Gesamte Backend-Suite**

Run: `cd backend && python -m pytest -x --timeout=120`
Expected: PASS (keine Regressionen).

- [ ] **Step 2: Frontend-Build**

Run: `cd client && npm run build`
Expected: erfolgreich.

- [ ] **Step 3: vectordb-Index aktualisieren**

Nach den größeren Änderungen den Suchindex inkrementell updaten (`mcp__vectordb-search__index_update`, projectPath `D:/Programme (x86)/Baluhost`).

- [ ] **Step 4: Manueller Prod-Smoketest (Operator, lokal am Server)**

Über die Companion-App: Authority einschalten → prüfen, dass `powerprofilesctl get` nicht mehr greift (`systemctl is-enabled power-profiles-daemon` = `masked`), `scaling_max_freq` fällt auf den Idle-Cap, `scaling_cur_freq` idle ~400 MHz. Spiel über Steam starten → Cap hebt sich, `scaling_cur_freq` boostet; Spiel beenden → nach ≤ ~4 s wieder gedeckelt. Authority ausschalten → PPD wieder aktiv.

- [ ] **Step 5: PR**

```bash
git push -u origin feat/cpu-power-authority
gh pr create --base main --title "feat(power): enforced CPU cap with allowlist boost (sole authority)" --body "<Zusammenfassung + Link auf Spec/Plan>"
```
> Release-Workflow: PR gegen `main` (kein lokaler Merge). CI muss grün sein.

---

## Self-Review (Plan ↔ Spec)

- **Spec §4.1 Enforcement-Loop** → Tasks 1–4. ✓
- **§4.2 PPD-Ownership** → Task 5. ✓
- **§4.3 Game-Session-Watcher** → Tasks 7–8. ✓
- **§4.4 Allowlist + Config** → Tasks 5 (config), 6 (Tabelle), 9 (CRUD). ✓
- **§4.5 UI** → Tasks 11–13. ✓
- **§6 Cap-Werte (400-Floor, Boost-Ziel)** → Task 2 (`_desired_config_for`). ✓
- **§7 Endpoints (local-only)** → Tasks 5, 9 (`require_local_admin`). ✓
- **§8 sudoers** → Task 10. ✓
- **§10 Tests** → in jeder Task TDD. ✓
- **Konsistenz der Symbole:** `read_enforcement_state` (T1) → genutzt in `_enforce_current_profile` (T3); `_desired_config_for` (T2) → T3, T11; `_boost_max_override` (T2) → T8; `load_authority_config`/`save_authority_config` (T5) → T8, T9; `list_boost_rules` (T8) → T9 CRUD; `match_boost_rules`/`ProcInfo`/`snapshot_processes` (T7/T8) konsistent. ✓
- **Offen (bewusst):** exakte sudoers-Dateinamen, realer `systemctl`-Pfad, realer `PowerStatusResponse`-Feldname (`frequency_range` vs `freq_range`), exakte `get_audit_logger_db`-Signatur, Frontend-Komponentenort — jeweils im Step vermerkt, beim Bauen am realen Code verifizieren.
