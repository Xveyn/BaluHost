# SleepConfigPanel F2 Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zerlege `components/power/SleepConfigPanel.tsx` (721 Zeilen, ~35 `useState`) in zwei Form-Hooks + ein Verzeichnis `components/power/sleep-config/` (8 Cards + Primitives), und reduziere das Panel auf ~150 Zeilen — behavior-preserving, plus breite Vitest-Abdeckung inkl. Panel-Integration.

**Architecture:** Der 30-useState-Smell wird echt beseitigt: `useSleepConfigForm` konsolidiert 20 Formfelder in EIN Objekt (`update`/`syncFromResponse`/`toPayload`), `useFritzBoxForm` die 6 FB-Felder (+ `config`/`testing`/`test`). Acht reine Präsentations-Cards konsumieren Form-Slices + `update`. Das Panel bleibt am selben Pfad (Barrel + Page-Import unberührt) und wird zum Orchestrator (load/save/state). Folgt dem `useGpuPower`-Draft-Muster.

**Tech Stack:** React 18 + TypeScript (strict), Tailwind, `react-i18next`, `lucide-react`, `react-hot-toast`, Vitest + `@testing-library/react`.

## Global Constraints

- **Behavior-preserving:** keine Änderung an Load-/Save-/Test-Logik, Payloads, Endpoints, Feldern, Default-Werten. `toPayload()` erzeugt das **byte-genau** gleiche `SleepConfigUpdate` bzw. `FritzBoxConfigUpdate` wie das aktuelle `handleSave`.
- **Kein i18n-Umbau:** hardcodierte Strings ("Auto-Idle Detection", "System Capabilities", "Save Configuration", "Erkannt: … Übernehmen?", etc.) **verbatim** übernehmen. Bestehende `t('sleep.…')`-Aufrufe (Presence/Schedule) verbatim in die jeweilige Card mitnehmen (`useTranslation('system')`).
- **Kein TanStack** für Sleep-Config/Fritz!Box (nutzer-getriggerte Config-Daten).
- **Test-Konvention (Assessment T7): keine Tailwind-Klassen-Assertions.** role/text/label/`getByRole('spinbutton'|'checkbox'|'combobox')`. `react-i18next` gemockt zu `t:(k)=>k`; API-Module + `react-hot-toast` gemockt.
- **Primitives bleiben sleep-config-lokal** (kein Promoten nach `ui/`).
- **Panel-Datei bleibt** `components/power/SleepConfigPanel.tsx`.
- **Windows/CRLF:** `core.autocrlf=true` → git "LF will be replaced by CRLF"-Warnung ist erwartbar. Shell-Befehle mit `;` verketten, **nie** `&&`.
- Jede `sleep-config/*`-Datei < ~200 Zeilen.

**Alle Befehle laufen aus `client/`** (`cd client` zuerst).

### Referenz — die exakten Typen (aus `api/sleep.ts` / `api/fritzbox.ts`)

`SleepConfigResponse` (Read) hat u. a. die 20 Formfelder + `core_uptime_enabled`, `core_uptime_suspend_on_exit`, `always_awake_*` (die das Panel **nicht** ins Formular mappt). `SleepConfigUpdate` = dieselben Keys optional. `ScheduleMode = 'soft'|'suspend'`, `PresenceMode = 'active'|'session'`.
`PresenceStatus = { enabled, mode, anyone_present, active_session_count, suppressing_suspend }`.
`SleepCapabilities = { hdparm_available, rtcwake_available, systemctl_available, can_suspend, wol_interfaces: string[], data_disk_devices: string[], own_mac_address: string|null }`.
`FritzBoxConfig = { host, port, username, nas_mac_address: string|null, enabled, has_password }`.
`FritzBoxConfigUpdate = { host?, port?, username?, password?, nas_mac_address?: string, enabled? }`.

---

### Task 1: `SleepFormControls.tsx` (Primitives)

**Files:**
- Create: `client/src/components/power/sleep-config/SleepFormControls.tsx`
- Test: `client/src/__tests__/components/power/sleep-config/SleepFormControls.test.tsx`

**Interfaces:**
- Produces:
  - `Toggle(props: { checked: boolean; onChange: (v: boolean) => void })`
  - `ToggleRow(props: { label: string; checked: boolean; onChange: (v: boolean) => void; icon?: React.ReactNode })`
  - `NumberInput(props: { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number })`

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/power/sleep-config/SleepFormControls.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Toggle, ToggleRow, NumberInput } from '../../../../components/power/sleep-config/SleepFormControls';

describe('SleepFormControls', () => {
  it('Toggle flips its value on click', () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('ToggleRow renders its label and toggles', () => {
    const onChange = vi.fn();
    render(<ToggleRow label="Pause monitoring" checked onChange={onChange} />);
    expect(screen.getByText('Pause monitoring')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button'));
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it('NumberInput reports a numeric value', () => {
    const onChange = vi.fn();
    render(<NumberInput label="Idle timeout (min)" value={15} onChange={onChange} />);
    // label and input are siblings (no htmlFor/id) -> use getByText for the label
    expect(screen.getByText('Idle timeout (min)')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '20' } });
    expect(onChange).toHaveBeenCalledWith(20);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/SleepFormControls.test.tsx`
Expected: FAIL — cannot find module `SleepFormControls`.

- [ ] **Step 3: Write the implementation (verbatim from the original panel, lines 536–605)**

```tsx
// client/src/components/power/sleep-config/SleepFormControls.tsx
export function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors ${
        checked ? 'bg-teal-500' : 'bg-slate-600'
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
          checked ? 'translate-x-5.5 ml-0.5' : 'translate-x-0.5'
        } mt-0.5`}
      />
    </button>
  );
}

export function ToggleRow({
  label,
  checked,
  onChange,
  icon,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-xs sm:text-sm text-slate-300">{label}</span>
      </div>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  );
}

export function NumberInput({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <label className="text-xs sm:text-sm text-slate-400 shrink-0">{label}</label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        min={min}
        max={max}
        step={step}
        className="w-24 rounded bg-slate-900 border border-slate-600 px-3 py-1.5 text-sm text-white text-right focus:border-teal-400 focus:outline-none"
      />
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/SleepFormControls.test.tsx`
Expected: PASS (3 tests). If the `getByLabelText` assertion fails (label not associated), swap it for `getByText` per the Step-1 note and re-run.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/sleep-config/SleepFormControls.tsx client/src/__tests__/components/power/sleep-config/SleepFormControls.test.tsx
git commit -m "feat(sleep): extract SleepFormControls primitives (Toggle/ToggleRow/NumberInput) (F2)"
```

---

### Task 2: `useSleepConfigForm.ts` hook

**Files:**
- Create: `client/src/hooks/useSleepConfigForm.ts`
- Test: `client/src/__tests__/hooks/useSleepConfigForm.test.ts`

**Interfaces:**
- Consumes: `SleepConfigResponse`, `SleepConfigUpdate`, `ScheduleMode`, `PresenceMode` from `../api/sleep`.
- Produces:
  ```ts
  interface SleepConfigForm { /* 20 fields, see impl */ }
  useSleepConfigForm(): {
    form: SleepConfigForm;
    update: (patch: Partial<SleepConfigForm>) => void;
    syncFromResponse: (c: SleepConfigResponse) => void;
    toPayload: () => SleepConfigUpdate;
  }
  ```
  `SleepConfigForm` is exported (cards import it for their `update` prop type).

- [ ] **Step 1: Write the failing test**

```ts
// client/src/__tests__/hooks/useSleepConfigForm.test.ts
import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSleepConfigForm } from '../../hooks/useSleepConfigForm';
import type { SleepConfigResponse, SleepConfigUpdate } from '../../api/sleep';

const response: SleepConfigResponse = {
  auto_idle_enabled: true, idle_timeout_minutes: 30, idle_cpu_threshold: 7.5,
  idle_disk_io_threshold: 1.0, idle_http_threshold: 10,
  auto_escalation_enabled: true, escalation_after_minutes: 90,
  schedule_enabled: true, schedule_sleep_time: '22:30', schedule_wake_time: '07:15',
  schedule_mode: 'suspend',
  wol_mac_address: 'AA:BB:CC:DD:EE:FF', wol_broadcast_address: '10.0.0.255',
  pause_monitoring: false, pause_disk_io: false, reduced_telemetry_interval: 45,
  disk_spindown_enabled: false,
  core_uptime_enabled: false, core_uptime_suspend_on_exit: false,
  presence_enabled: false, presence_mode: 'session', presence_timeout_minutes: 5,
};

describe('useSleepConfigForm', () => {
  it('has sensible defaults before sync', () => {
    const { result } = renderHook(() => useSleepConfigForm());
    expect(result.current.form.idleTimeout).toBe(15);
    expect(result.current.form.pauseMonitoring).toBe(true);
    expect(result.current.form.presenceMode).toBe('active');
  });

  it('round-trips response -> syncFromResponse -> toPayload', () => {
    const { result } = renderHook(() => useSleepConfigForm());
    act(() => result.current.syncFromResponse(response));

    const expected: SleepConfigUpdate = {
      auto_idle_enabled: true, idle_timeout_minutes: 30, idle_cpu_threshold: 7.5,
      idle_disk_io_threshold: 1.0, idle_http_threshold: 10,
      auto_escalation_enabled: true, escalation_after_minutes: 90,
      schedule_enabled: true, schedule_sleep_time: '22:30', schedule_wake_time: '07:15',
      schedule_mode: 'suspend',
      wol_mac_address: 'AA:BB:CC:DD:EE:FF', wol_broadcast_address: '10.0.0.255',
      pause_monitoring: false, pause_disk_io: false, reduced_telemetry_interval: 45,
      disk_spindown_enabled: false,
      presence_enabled: false, presence_mode: 'session', presence_timeout_minutes: 5,
    };
    expect(result.current.toPayload()).toEqual(expected);
  });

  it('maps empty WoL strings to null in the payload', () => {
    const { result } = renderHook(() => useSleepConfigForm());
    act(() => result.current.syncFromResponse({ ...response, wol_mac_address: null, wol_broadcast_address: null }));
    const payload = result.current.toPayload();
    expect(payload.wol_mac_address).toBeNull();
    expect(payload.wol_broadcast_address).toBeNull();
  });

  it('update patches one field without clobbering others', () => {
    const { result } = renderHook(() => useSleepConfigForm());
    act(() => result.current.update({ idleTimeout: 99 }));
    expect(result.current.form.idleTimeout).toBe(99);
    expect(result.current.form.pauseMonitoring).toBe(true); // untouched default
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/hooks/useSleepConfigForm.test.ts`
Expected: FAIL — cannot find module `useSleepConfigForm`.

- [ ] **Step 3: Write the implementation**

```ts
// client/src/hooks/useSleepConfigForm.ts
import { useState, useCallback } from 'react';
import type { SleepConfigResponse, SleepConfigUpdate, ScheduleMode, PresenceMode } from '../api/sleep';

export interface SleepConfigForm {
  autoIdleEnabled: boolean;
  idleTimeout: number;
  idleCpuThreshold: number;
  idleDiskIoThreshold: number;
  idleHttpThreshold: number;
  escalationEnabled: boolean;
  escalationMinutes: number;
  scheduleEnabled: boolean;
  scheduleSleepTime: string;
  scheduleWakeTime: string;
  scheduleMode: ScheduleMode;
  wolMac: string;
  wolBroadcast: string;
  pauseMonitoring: boolean;
  pauseDiskIo: boolean;
  reducedTelemetry: number;
  diskSpindown: boolean;
  presenceEnabled: boolean;
  presenceMode: PresenceMode;
  presenceTimeout: number;
}

const DEFAULT_FORM: SleepConfigForm = {
  autoIdleEnabled: false,
  idleTimeout: 15,
  idleCpuThreshold: 5.0,
  idleDiskIoThreshold: 0.5,
  idleHttpThreshold: 5.0,
  escalationEnabled: false,
  escalationMinutes: 60,
  scheduleEnabled: false,
  scheduleSleepTime: '23:00',
  scheduleWakeTime: '06:00',
  scheduleMode: 'soft',
  wolMac: '',
  wolBroadcast: '',
  pauseMonitoring: true,
  pauseDiskIo: true,
  reducedTelemetry: 30,
  diskSpindown: true,
  presenceEnabled: true,
  presenceMode: 'active',
  presenceTimeout: 3,
};

export interface UseSleepConfigFormResult {
  form: SleepConfigForm;
  update: (patch: Partial<SleepConfigForm>) => void;
  syncFromResponse: (c: SleepConfigResponse) => void;
  toPayload: () => SleepConfigUpdate;
}

export function useSleepConfigForm(): UseSleepConfigFormResult {
  const [form, setForm] = useState<SleepConfigForm>(DEFAULT_FORM);

  const update = useCallback((patch: Partial<SleepConfigForm>) => {
    setForm((f) => ({ ...f, ...patch }));
  }, []);

  const syncFromResponse = useCallback((c: SleepConfigResponse) => {
    setForm({
      autoIdleEnabled: c.auto_idle_enabled,
      idleTimeout: c.idle_timeout_minutes,
      idleCpuThreshold: c.idle_cpu_threshold,
      idleDiskIoThreshold: c.idle_disk_io_threshold,
      idleHttpThreshold: c.idle_http_threshold,
      escalationEnabled: c.auto_escalation_enabled,
      escalationMinutes: c.escalation_after_minutes,
      scheduleEnabled: c.schedule_enabled,
      scheduleSleepTime: c.schedule_sleep_time,
      scheduleWakeTime: c.schedule_wake_time,
      scheduleMode: c.schedule_mode,
      wolMac: c.wol_mac_address || '',
      wolBroadcast: c.wol_broadcast_address || '',
      pauseMonitoring: c.pause_monitoring,
      pauseDiskIo: c.pause_disk_io,
      reducedTelemetry: c.reduced_telemetry_interval,
      diskSpindown: c.disk_spindown_enabled,
      presenceEnabled: c.presence_enabled,
      presenceMode: c.presence_mode,
      presenceTimeout: c.presence_timeout_minutes,
    });
  }, []);

  const toPayload = useCallback((): SleepConfigUpdate => ({
    auto_idle_enabled: form.autoIdleEnabled,
    idle_timeout_minutes: form.idleTimeout,
    idle_cpu_threshold: form.idleCpuThreshold,
    idle_disk_io_threshold: form.idleDiskIoThreshold,
    idle_http_threshold: form.idleHttpThreshold,
    auto_escalation_enabled: form.escalationEnabled,
    escalation_after_minutes: form.escalationMinutes,
    schedule_enabled: form.scheduleEnabled,
    schedule_sleep_time: form.scheduleSleepTime,
    schedule_wake_time: form.scheduleWakeTime,
    schedule_mode: form.scheduleMode,
    wol_mac_address: form.wolMac || null,
    wol_broadcast_address: form.wolBroadcast || null,
    pause_monitoring: form.pauseMonitoring,
    pause_disk_io: form.pauseDiskIo,
    reduced_telemetry_interval: form.reducedTelemetry,
    disk_spindown_enabled: form.diskSpindown,
    presence_enabled: form.presenceEnabled,
    presence_mode: form.presenceMode,
    presence_timeout_minutes: form.presenceTimeout,
  }), [form]);

  return { form, update, syncFromResponse, toPayload };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/hooks/useSleepConfigForm.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useSleepConfigForm.ts client/src/__tests__/hooks/useSleepConfigForm.test.ts
git commit -m "feat(sleep): add useSleepConfigForm (consolidate 20 fields into one object) (F2)"
```

---

### Task 3: `useFritzBoxForm.ts` hook

**Files:**
- Create: `client/src/hooks/useFritzBoxForm.ts`
- Test: `client/src/__tests__/hooks/useFritzBoxForm.test.ts`

**Interfaces:**
- Consumes: `testFritzBoxConnection`, `FritzBoxConfig`, `FritzBoxConfigUpdate` from `../api/fritzbox`; `react-hot-toast`.
- Produces:
  ```ts
  interface FritzBoxForm { host: string; port: number; username: string; password: string; mac: string; enabled: boolean; }
  useFritzBoxForm(): {
    form: FritzBoxForm;
    update: (patch: Partial<FritzBoxForm>) => void;
    config: FritzBoxConfig | null;
    syncFromConfig: (fb: FritzBoxConfig) => void;
    toPayload: () => FritzBoxConfigUpdate;
    testing: boolean;
    test: () => Promise<void>;
  }
  ```

- [ ] **Step 1: Write the failing test**

```ts
// client/src/__tests__/hooks/useFritzBoxForm.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../api/fritzbox', () => ({ testFritzBoxConnection: vi.fn() }));

import toast from 'react-hot-toast';
import { testFritzBoxConnection, type FritzBoxConfig } from '../../api/fritzbox';
import { useFritzBoxForm } from '../../hooks/useFritzBoxForm';

const fb: FritzBoxConfig = {
  host: '192.168.1.1', port: 12345, username: 'admin',
  nas_mac_address: '11:22:33:44:55:66', enabled: true, has_password: true,
};

beforeEach(() => vi.clearAllMocks());

describe('useFritzBoxForm', () => {
  it('syncFromConfig fills the form but leaves password empty', () => {
    const { result } = renderHook(() => useFritzBoxForm());
    act(() => result.current.syncFromConfig(fb));
    expect(result.current.form.host).toBe('192.168.1.1');
    expect(result.current.form.mac).toBe('11:22:33:44:55:66');
    expect(result.current.form.enabled).toBe(true);
    expect(result.current.form.password).toBe('');
    expect(result.current.config?.has_password).toBe(true);
  });

  it('toPayload omits password when empty and maps empty mac to undefined', () => {
    const { result } = renderHook(() => useFritzBoxForm());
    act(() => result.current.update({ host: 'h', port: 1, username: 'u', mac: '', enabled: false }));
    const payload = result.current.toPayload();
    expect('password' in payload).toBe(false);
    expect(payload.nas_mac_address).toBeUndefined();
    expect(payload).toMatchObject({ host: 'h', port: 1, username: 'u', enabled: false });
  });

  it('toPayload includes password when set', () => {
    const { result } = renderHook(() => useFritzBoxForm());
    act(() => result.current.update({ password: 'secret' }));
    expect(result.current.toPayload().password).toBe('secret');
  });

  it('test() toasts success/error and clears testing', async () => {
    (testFritzBoxConnection as any).mockResolvedValue({ success: true, message: 'OK' });
    const { result } = renderHook(() => useFritzBoxForm());
    await act(async () => { await result.current.test(); });
    expect(toast.success).toHaveBeenCalledWith('OK');
    expect(result.current.testing).toBe(false);

    (testFritzBoxConnection as any).mockResolvedValue({ success: false, message: 'bad' });
    await act(async () => { await result.current.test(); });
    expect(toast.error).toHaveBeenCalledWith('bad');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/hooks/useFritzBoxForm.test.ts`
Expected: FAIL — cannot find module `useFritzBoxForm`.

- [ ] **Step 3: Write the implementation**

```ts
// client/src/hooks/useFritzBoxForm.ts
import { useState, useCallback } from 'react';
import toast from 'react-hot-toast';
import { testFritzBoxConnection, type FritzBoxConfig, type FritzBoxConfigUpdate } from '../api/fritzbox';

export interface FritzBoxForm {
  host: string;
  port: number;
  username: string;
  password: string;
  mac: string;
  enabled: boolean;
}

const DEFAULT_FB_FORM: FritzBoxForm = {
  host: '192.168.178.1',
  port: 49000,
  username: '',
  password: '',
  mac: '',
  enabled: false,
};

export interface UseFritzBoxFormResult {
  form: FritzBoxForm;
  update: (patch: Partial<FritzBoxForm>) => void;
  config: FritzBoxConfig | null;
  syncFromConfig: (fb: FritzBoxConfig) => void;
  toPayload: () => FritzBoxConfigUpdate;
  testing: boolean;
  test: () => Promise<void>;
}

export function useFritzBoxForm(): UseFritzBoxFormResult {
  const [form, setForm] = useState<FritzBoxForm>(DEFAULT_FB_FORM);
  const [config, setConfig] = useState<FritzBoxConfig | null>(null);
  const [testing, setTesting] = useState(false);

  const update = useCallback((patch: Partial<FritzBoxForm>) => {
    setForm((f) => ({ ...f, ...patch }));
  }, []);

  const syncFromConfig = useCallback((fb: FritzBoxConfig) => {
    setConfig(fb);
    setForm((f) => ({
      ...f,
      host: fb.host,
      port: fb.port,
      username: fb.username,
      mac: fb.nas_mac_address || '',
      enabled: fb.enabled,
      // password intentionally left as-is (API never returns it)
    }));
  }, []);

  const toPayload = useCallback((): FritzBoxConfigUpdate => ({
    host: form.host,
    port: form.port,
    username: form.username,
    ...(form.password ? { password: form.password } : {}),
    nas_mac_address: form.mac || undefined,
    enabled: form.enabled,
  }), [form]);

  const test = useCallback(async () => {
    setTesting(true);
    try {
      const result = await testFritzBoxConnection();
      if (result.success) {
        toast.success(result.message);
      } else {
        toast.error(result.message);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Connection test failed');
    } finally {
      setTesting(false);
    }
  }, []);

  return { form, update, config, syncFromConfig, toPayload, testing, test };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/hooks/useFritzBoxForm.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useFritzBoxForm.ts client/src/__tests__/hooks/useFritzBoxForm.test.ts
git commit -m "feat(sleep): add useFritzBoxForm (state + toPayload + test) (F2)"
```

---

### Task 4: `CapabilitiesCard.tsx`

**Files:**
- Create: `client/src/components/power/sleep-config/CapabilitiesCard.tsx`
- Test: `client/src/__tests__/components/power/sleep-config/CapabilitiesCard.test.tsx`

**Interfaces:**
- Consumes: `SleepCapabilities` from `../../../api/sleep`; icons from `lucide-react`.
- Produces: `CapabilitiesCard(props: { capabilities: SleepCapabilities; helpOpen: boolean; onToggleHelp: () => void })`. Internally owns `CapBadge`, `CapabilityHelp`, `getHelpEntries`, `HelpEntry` (all moved verbatim from the panel).

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/power/sleep-config/CapabilitiesCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CapabilitiesCard } from '../../../../components/power/sleep-config/CapabilitiesCard';
import type { SleepCapabilities } from '../../../../api/sleep';

const caps = (over: Partial<SleepCapabilities> = {}): SleepCapabilities => ({
  hdparm_available: true, rtcwake_available: true, systemctl_available: true,
  can_suspend: true, wol_interfaces: ['eth0'], data_disk_devices: ['sda'],
  own_mac_address: 'AA:BB:CC:DD:EE:FF', ...over,
});

describe('CapabilitiesCard', () => {
  it('renders capability badges', () => {
    render(<CapabilitiesCard capabilities={caps()} helpOpen={false} onToggleHelp={vi.fn()} />);
    expect(screen.getByText('hdparm')).toBeInTheDocument();
    expect(screen.getByText('rtcwake')).toBeInTheDocument();
  });

  it('shows Setup Help only when a capability is missing', () => {
    const { rerender } = render(<CapabilitiesCard capabilities={caps()} helpOpen={false} onToggleHelp={vi.fn()} />);
    expect(screen.queryByText('Setup Help')).toBeNull(); // all present -> no help

    rerender(<CapabilitiesCard capabilities={caps({ hdparm_available: false })} helpOpen={false} onToggleHelp={vi.fn()} />);
    expect(screen.getByText('Setup Help')).toBeInTheDocument();
  });

  it('fires onToggleHelp when the help button is clicked', () => {
    const onToggleHelp = vi.fn();
    render(<CapabilitiesCard capabilities={caps({ can_suspend: false })} helpOpen={false} onToggleHelp={onToggleHelp} />);
    fireEvent.click(screen.getByText('Setup Help'));
    expect(onToggleHelp).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/CapabilitiesCard.test.tsx`
Expected: FAIL — cannot find module `CapabilitiesCard`.

- [ ] **Step 3: Write the implementation (card wrapper new; CapBadge/CapabilityHelp/getHelpEntries verbatim from panel lines 607–720)**

```tsx
// client/src/components/power/sleep-config/CapabilitiesCard.tsx
import { Settings, Terminal, ChevronDown } from 'lucide-react';
import type { SleepCapabilities } from '../../../api/sleep';

export function CapabilitiesCard({
  capabilities,
  helpOpen,
  onToggleHelp,
}: {
  capabilities: SleepCapabilities;
  helpOpen: boolean;
  onToggleHelp: () => void;
}) {
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6">
      <h4 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
        <Settings className="h-4 w-4 text-slate-400" />
        System Capabilities
      </h4>
      <div className="flex flex-wrap gap-2">
        <CapBadge label="hdparm" ok={capabilities.hdparm_available} />
        <CapBadge label="rtcwake" ok={capabilities.rtcwake_available} />
        <CapBadge label="systemctl" ok={capabilities.systemctl_available} />
        <CapBadge label="Suspend" ok={capabilities.can_suspend} />
        <CapBadge label={`WoL (${capabilities.wol_interfaces.length} ifaces)`} ok={capabilities.wol_interfaces.length > 0} />
        <CapBadge label={`${capabilities.data_disk_devices.length} data disks`} ok={capabilities.data_disk_devices.length > 0} />
      </div>
      <CapabilityHelp capabilities={capabilities} open={helpOpen} onToggle={onToggleHelp} />
    </div>
  );
}

interface HelpEntry {
  key: string;
  title: string;
  description: string;
  commands: string[];
}

function getHelpEntries(caps: SleepCapabilities): HelpEntry[] {
  const entries: HelpEntry[] = [];
  if (!caps.hdparm_available) {
    entries.push({
      key: 'hdparm',
      title: 'hdparm — Disk Spindown Tool',
      description: 'Required to spin down data disks during sleep.',
      commands: ['sudo apt install hdparm', 'hdparm -C /dev/sdX   # verify standby support'],
    });
  }
  if (!caps.can_suspend) {
    entries.push({
      key: 'suspend',
      title: 'Suspend (S3 Sleep)',
      description: 'System must support S3 suspend-to-RAM.',
      commands: ['cat /sys/power/state   # should contain "mem"', '# If missing: enable S3 (Suspend to RAM) in BIOS/UEFI'],
    });
  }
  if (caps.wol_interfaces.length === 0) {
    entries.push({
      key: 'wol',
      title: 'Wake-on-LAN',
      description: 'Requires ethtool and a NIC with WoL support. Also enable WoL in BIOS.',
      commands: [
        'sudo apt install ethtool',
        'sudo ethtool -s <iface> wol g',
        '# Persistent (systemd-networkd):',
        '# /etc/systemd/network/10-<iface>.link',
        '# [Link]',
        '# WakeOnLan=magic',
      ],
    });
  }
  if (!caps.rtcwake_available) {
    entries.push({
      key: 'rtcwake',
      title: 'rtcwake — Timed Wake-up',
      description: 'Part of util-linux (usually pre-installed).',
      commands: ['ls /dev/rtc*   # check for RTC device', 'sudo apt install util-linux'],
    });
  }
  if (!caps.systemctl_available) {
    entries.push({
      key: 'systemctl',
      title: 'systemctl — Systemd Control',
      description: 'Part of systemd (pre-installed on Debian/Ubuntu).',
      commands: ['systemctl --version   # verify installation', 'sudo apt install systemd'],
    });
  }
  return entries;
}

function CapabilityHelp({
  capabilities,
  open,
  onToggle,
}: {
  capabilities: SleepCapabilities;
  open: boolean;
  onToggle: () => void;
}) {
  const entries = getHelpEntries(capabilities);
  if (entries.length === 0) return null;

  return (
    <div className="mt-3">
      <button
        onClick={onToggle}
        className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
      >
        <Terminal className="h-3.5 w-3.5" />
        Setup Help
        <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>

      <div
        className={`grid transition-[grid-template-rows] duration-200 ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
      >
        <div className="overflow-hidden">
          <div className="pt-3 space-y-3">
            {entries.map((entry) => (
              <div key={entry.key} className="rounded-lg bg-slate-800/60 border border-slate-700/40 p-3">
                <h5 className="text-xs font-medium text-slate-200 mb-1">{entry.title}</h5>
                <p className="text-xs text-slate-400 mb-2">{entry.description}</p>
                <pre className="bg-slate-900/80 border border-slate-700/50 rounded px-3 py-2 font-mono text-xs text-slate-300 overflow-x-auto">
                  {entry.commands.join('\n')}
                </pre>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function CapBadge({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
        ok ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-700/50 text-slate-500'
      }`}
    >
      {ok ? '✓' : '✗'} {label}
    </span>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/CapabilitiesCard.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/sleep-config/CapabilitiesCard.tsx client/src/__tests__/components/power/sleep-config/CapabilitiesCard.test.tsx
git commit -m "feat(sleep): extract CapabilitiesCard (badges + setup help) (F2)"
```

---

### Task 5: `IdleDetectionCard.tsx`

**Files:**
- Create: `client/src/components/power/sleep-config/IdleDetectionCard.tsx`
- Test: `client/src/__tests__/components/power/sleep-config/IdleDetectionCard.test.tsx`

**Interfaces:**
- Consumes: `Toggle`, `NumberInput` from `./SleepFormControls`; `SleepConfigForm` from `../../../hooks/useSleepConfigForm`; `Timer` from `lucide-react`.
- Produces: `IdleDetectionCard(props: Pick<SleepConfigForm, 'autoIdleEnabled'|'idleTimeout'|'idleCpuThreshold'|'idleDiskIoThreshold'|'idleHttpThreshold'> & { update: (patch: Partial<SleepConfigForm>) => void })`.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/power/sleep-config/IdleDetectionCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IdleDetectionCard } from '../../../../components/power/sleep-config/IdleDetectionCard';

const base = {
  autoIdleEnabled: false, idleTimeout: 15, idleCpuThreshold: 5,
  idleDiskIoThreshold: 0.5, idleHttpThreshold: 5, update: vi.fn(),
};

describe('IdleDetectionCard', () => {
  it('hides the detail inputs when disabled', () => {
    render(<IdleDetectionCard {...base} autoIdleEnabled={false} />);
    expect(screen.queryByText('Idle timeout (min)')).toBeNull();
  });

  it('shows the detail inputs when enabled', () => {
    render(<IdleDetectionCard {...base} autoIdleEnabled />);
    expect(screen.getByText('Idle timeout (min)')).toBeInTheDocument();
    expect(screen.getByText('CPU threshold (%)')).toBeInTheDocument();
  });

  it('toggling calls update with autoIdleEnabled', () => {
    const update = vi.fn();
    render(<IdleDetectionCard {...base} update={update} />);
    fireEvent.click(screen.getByRole('button'));
    expect(update).toHaveBeenCalledWith({ autoIdleEnabled: true });
  });

  it('editing a number input calls update with the field', () => {
    const update = vi.fn();
    render(<IdleDetectionCard {...base} autoIdleEnabled update={update} />);
    fireEvent.change(screen.getAllByRole('spinbutton')[0], { target: { value: '42' } });
    expect(update).toHaveBeenCalledWith({ idleTimeout: 42 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/IdleDetectionCard.test.tsx`
Expected: FAIL — cannot find module `IdleDetectionCard`.

- [ ] **Step 3: Write the implementation**

```tsx
// client/src/components/power/sleep-config/IdleDetectionCard.tsx
import { Timer } from 'lucide-react';
import { Toggle, NumberInput } from './SleepFormControls';
import type { SleepConfigForm } from '../../../hooks/useSleepConfigForm';

type IdleDetectionCardProps = Pick<
  SleepConfigForm,
  'autoIdleEnabled' | 'idleTimeout' | 'idleCpuThreshold' | 'idleDiskIoThreshold' | 'idleHttpThreshold'
> & { update: (patch: Partial<SleepConfigForm>) => void };

export function IdleDetectionCard({
  autoIdleEnabled, idleTimeout, idleCpuThreshold, idleDiskIoThreshold, idleHttpThreshold, update,
}: IdleDetectionCardProps) {
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-white flex items-center gap-2">
          <Timer className="h-4 w-4 text-blue-400" />
          Auto-Idle Detection
        </h4>
        <Toggle checked={autoIdleEnabled} onChange={(v) => update({ autoIdleEnabled: v })} />
      </div>

      {autoIdleEnabled && (
        <div className="space-y-3 pl-1">
          <NumberInput label="Idle timeout (min)" value={idleTimeout} onChange={(v) => update({ idleTimeout: v })} min={1} max={1440} />
          <NumberInput label="CPU threshold (%)" value={idleCpuThreshold} onChange={(v) => update({ idleCpuThreshold: v })} min={0} max={100} step={0.5} />
          <NumberInput label="Disk I/O threshold (MB/s)" value={idleDiskIoThreshold} onChange={(v) => update({ idleDiskIoThreshold: v })} min={0} step={0.1} />
          <NumberInput label="HTTP req/min threshold" value={idleHttpThreshold} onChange={(v) => update({ idleHttpThreshold: v })} min={0} step={1} />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/IdleDetectionCard.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/sleep-config/IdleDetectionCard.tsx client/src/__tests__/components/power/sleep-config/IdleDetectionCard.test.tsx
git commit -m "feat(sleep): extract IdleDetectionCard (F2)"
```

---

### Task 6: `EscalationCard.tsx`

**Files:**
- Create: `client/src/components/power/sleep-config/EscalationCard.tsx`
- Test: `client/src/__tests__/components/power/sleep-config/EscalationCard.test.tsx`

**Interfaces:**
- Produces: `EscalationCard(props: Pick<SleepConfigForm, 'escalationEnabled'|'escalationMinutes'> & { update: (patch: Partial<SleepConfigForm>) => void })`.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/power/sleep-config/EscalationCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EscalationCard } from '../../../../components/power/sleep-config/EscalationCard';

const base = { escalationEnabled: false, escalationMinutes: 60, update: vi.fn() };

describe('EscalationCard', () => {
  it('hides the minutes input when disabled', () => {
    render(<EscalationCard {...base} />);
    expect(screen.queryByText('Escalate after (min)')).toBeNull();
  });

  it('shows the minutes input when enabled and edits it', () => {
    const update = vi.fn();
    render(<EscalationCard {...base} escalationEnabled update={update} />);
    expect(screen.getByText('Escalate after (min)')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '30' } });
    expect(update).toHaveBeenCalledWith({ escalationMinutes: 30 });
  });

  it('toggle calls update with escalationEnabled', () => {
    const update = vi.fn();
    render(<EscalationCard {...base} update={update} />);
    fireEvent.click(screen.getByRole('button'));
    expect(update).toHaveBeenCalledWith({ escalationEnabled: true });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/EscalationCard.test.tsx`
Expected: FAIL — cannot find module.

- [ ] **Step 3: Write the implementation**

```tsx
// client/src/components/power/sleep-config/EscalationCard.tsx
import { TrendingUp } from 'lucide-react';
import { Toggle, NumberInput } from './SleepFormControls';
import type { SleepConfigForm } from '../../../hooks/useSleepConfigForm';

type EscalationCardProps = Pick<SleepConfigForm, 'escalationEnabled' | 'escalationMinutes'> & {
  update: (patch: Partial<SleepConfigForm>) => void;
};

export function EscalationCard({ escalationEnabled, escalationMinutes, update }: EscalationCardProps) {
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-white flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-purple-400" />
          Auto-Escalation (Soft Sleep → Suspend)
        </h4>
        <Toggle checked={escalationEnabled} onChange={(v) => update({ escalationEnabled: v })} />
      </div>

      {escalationEnabled && (
        <div className="pl-1">
          <NumberInput label="Escalate after (min)" value={escalationMinutes} onChange={(v) => update({ escalationMinutes: v })} min={1} max={1440} />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/EscalationCard.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/sleep-config/EscalationCard.tsx client/src/__tests__/components/power/sleep-config/EscalationCard.test.tsx
git commit -m "feat(sleep): extract EscalationCard (F2)"
```

---

### Task 7: `PresenceCard.tsx`

**Files:**
- Create: `client/src/components/power/sleep-config/PresenceCard.tsx`
- Test: `client/src/__tests__/components/power/sleep-config/PresenceCard.test.tsx`

**Interfaces:**
- Consumes: `Toggle`, `NumberInput` from `./SleepFormControls`; `SleepConfigForm`; `PresenceMode`, `PresenceStatus` from `../../../api/sleep`; `useTranslation`; `Eye` icon.
- Produces: `PresenceCard(props: Pick<SleepConfigForm, 'presenceEnabled'|'presenceMode'|'presenceTimeout'> & { update: (patch: Partial<SleepConfigForm>) => void; presenceStatus: PresenceStatus | null })`.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/power/sleep-config/PresenceCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { PresenceCard } from '../../../../components/power/sleep-config/PresenceCard';
import type { PresenceStatus } from '../../../../api/sleep';

const base = { presenceEnabled: true, presenceMode: 'active' as const, presenceTimeout: 3, update: vi.fn(), presenceStatus: null };

describe('PresenceCard', () => {
  it('shows mode select + timeout when enabled', () => {
    render(<PresenceCard {...base} />);
    expect(screen.getByRole('combobox')).toBeInTheDocument();
    expect(screen.getByText('sleep.presence.timeoutLabel')).toBeInTheDocument();
  });

  it('hides details when disabled', () => {
    render(<PresenceCard {...base} presenceEnabled={false} />);
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('shows the suppressing banner when presenceStatus.suppressing_suspend', () => {
    const status: PresenceStatus = { enabled: true, mode: 'active', anyone_present: true, active_session_count: 2, suppressing_suspend: true };
    render(<PresenceCard {...base} presenceStatus={status} />);
    expect(screen.getByText('sleep.presence.suppressing')).toBeInTheDocument();
  });

  it('changing mode calls update', () => {
    const update = vi.fn();
    render(<PresenceCard {...base} update={update} />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'session' } });
    expect(update).toHaveBeenCalledWith({ presenceMode: 'session' });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/PresenceCard.test.tsx`
Expected: FAIL — cannot find module.

- [ ] **Step 3: Write the implementation (t-calls verbatim from panel lines 270–309)**

```tsx
// client/src/components/power/sleep-config/PresenceCard.tsx
import { useTranslation } from 'react-i18next';
import { Eye } from 'lucide-react';
import { Toggle, NumberInput } from './SleepFormControls';
import type { SleepConfigForm } from '../../../hooks/useSleepConfigForm';
import type { PresenceMode, PresenceStatus } from '../../../api/sleep';

type PresenceCardProps = Pick<SleepConfigForm, 'presenceEnabled' | 'presenceMode' | 'presenceTimeout'> & {
  update: (patch: Partial<SleepConfigForm>) => void;
  presenceStatus: PresenceStatus | null;
};

export function PresenceCard({ presenceEnabled, presenceMode, presenceTimeout, update, presenceStatus }: PresenceCardProps) {
  const { t } = useTranslation('system');
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-white flex items-center gap-2">
          <Eye className="h-4 w-4 text-emerald-400" />
          {t('sleep.presence.title')}
        </h4>
        <Toggle checked={presenceEnabled} onChange={(v) => update({ presenceEnabled: v })} />
      </div>
      <p className="text-xs text-slate-400">{t('sleep.presence.description')}</p>

      {presenceEnabled && (
        <div className="space-y-3 pl-1">
          <div>
            <label className="block text-xs text-slate-400 mb-1">{t('sleep.presence.modeLabel')}</label>
            <select
              value={presenceMode}
              onChange={(e) => update({ presenceMode: e.target.value as PresenceMode })}
              className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none"
            >
              <option value="active">{t('sleep.presence.modeActive')}</option>
              <option value="session">{t('sleep.presence.modeSession')}</option>
            </select>
            <p className="mt-1 text-xs text-slate-500">{t('sleep.presence.modeHint')}</p>
          </div>
          <NumberInput
            label={t('sleep.presence.timeoutLabel')}
            value={presenceTimeout}
            onChange={(v) => update({ presenceTimeout: v })}
            min={1}
            max={60}
          />
          {presenceStatus?.suppressing_suspend && (
            <div className="rounded border border-emerald-500/20 bg-emerald-500/10 p-2 text-xs text-emerald-300">
              {t('sleep.presence.suppressing', { count: presenceStatus.active_session_count })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/PresenceCard.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/sleep-config/PresenceCard.tsx client/src/__tests__/components/power/sleep-config/PresenceCard.test.tsx
git commit -m "feat(sleep): extract PresenceCard (F2)"
```

---

### Task 8: `ScheduleCard.tsx`

**Files:**
- Create: `client/src/components/power/sleep-config/ScheduleCard.tsx`
- Test: `client/src/__tests__/components/power/sleep-config/ScheduleCard.test.tsx`

**Interfaces:**
- Consumes: `Toggle` from `./SleepFormControls`; `SleepConfigForm`; `ScheduleMode` from `../../../api/sleep`; `useTranslation`; `Clock` icon.
- Produces: `ScheduleCard(props: Pick<SleepConfigForm, 'scheduleEnabled'|'scheduleSleepTime'|'scheduleWakeTime'|'scheduleMode'> & { update: (patch: Partial<SleepConfigForm>) => void; coreUptimeMasterOn: boolean; alwaysAwakeOn: boolean })`.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/power/sleep-config/ScheduleCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { ScheduleCard } from '../../../../components/power/sleep-config/ScheduleCard';

const base = {
  scheduleEnabled: true, scheduleSleepTime: '23:00', scheduleWakeTime: '06:00',
  scheduleMode: 'soft' as const, update: vi.fn(), coreUptimeMasterOn: false, alwaysAwakeOn: false,
};

describe('ScheduleCard', () => {
  it('hides schedule detail when disabled', () => {
    render(<ScheduleCard {...base} scheduleEnabled={false} />);
    expect(screen.queryByText('Sleep at')).toBeNull();
  });

  it('shows the time inputs + mode when enabled', () => {
    render(<ScheduleCard {...base} />);
    expect(screen.getByText('Sleep at')).toBeInTheDocument();
    expect(screen.getByText('Wake at')).toBeInTheDocument();
  });

  it('shows the core-uptime override banner', () => {
    render(<ScheduleCard {...base} coreUptimeMasterOn />);
    expect(screen.getByText('sleep.coreUptime.scheduleOverride')).toBeInTheDocument();
  });

  it('shows the always-awake hint banner', () => {
    render(<ScheduleCard {...base} alwaysAwakeOn />);
    expect(screen.getByText('sleep.alwaysAwake.scheduleHint')).toBeInTheDocument();
  });

  it('editing the sleep time calls update', () => {
    const update = vi.fn();
    const { container } = render(<ScheduleCard {...base} update={update} />);
    const timeInputs = container.querySelectorAll('input[type="time"]');
    fireEvent.change(timeInputs[0], { target: { value: '22:00' } });
    expect(update).toHaveBeenCalledWith({ scheduleSleepTime: '22:00' });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/ScheduleCard.test.tsx`
Expected: FAIL — cannot find module.

- [ ] **Step 3: Write the implementation (verbatim from panel lines 311–366; t-calls kept)**

```tsx
// client/src/components/power/sleep-config/ScheduleCard.tsx
import { useTranslation } from 'react-i18next';
import { Clock } from 'lucide-react';
import { Toggle } from './SleepFormControls';
import type { SleepConfigForm } from '../../../hooks/useSleepConfigForm';
import type { ScheduleMode } from '../../../api/sleep';

type ScheduleCardProps = Pick<
  SleepConfigForm,
  'scheduleEnabled' | 'scheduleSleepTime' | 'scheduleWakeTime' | 'scheduleMode'
> & {
  update: (patch: Partial<SleepConfigForm>) => void;
  coreUptimeMasterOn: boolean;
  alwaysAwakeOn: boolean;
};

export function ScheduleCard({
  scheduleEnabled, scheduleSleepTime, scheduleWakeTime, scheduleMode, update, coreUptimeMasterOn, alwaysAwakeOn,
}: ScheduleCardProps) {
  const { t } = useTranslation('system');
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-white flex items-center gap-2">
          <Clock className="h-4 w-4 text-amber-400" />
          Sleep Schedule
        </h4>
        <Toggle checked={scheduleEnabled} onChange={(v) => update({ scheduleEnabled: v })} />
      </div>

      {scheduleEnabled && (
        <div className="space-y-3 pl-1">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Sleep at</label>
              <input
                type="time"
                value={scheduleSleepTime}
                onChange={(e) => update({ scheduleSleepTime: e.target.value })}
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Wake at</label>
              <input
                type="time"
                value={scheduleWakeTime}
                onChange={(e) => update({ scheduleWakeTime: e.target.value })}
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Schedule Mode</label>
            <select
              value={scheduleMode}
              onChange={(e) => update({ scheduleMode: e.target.value as ScheduleMode })}
              className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none"
            >
              <option value="soft">Soft Sleep</option>
              <option value="suspend">True Suspend</option>
            </select>
          </div>
          {coreUptimeMasterOn && (
            <div className="mt-2 rounded border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-300">
              {t('sleep.coreUptime.scheduleOverride')}
            </div>
          )}
          {alwaysAwakeOn && (
            <div className="mt-2 rounded border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-300">
              {t('sleep.alwaysAwake.scheduleHint')}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/ScheduleCard.test.tsx`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/sleep-config/ScheduleCard.tsx client/src/__tests__/components/power/sleep-config/ScheduleCard.test.tsx
git commit -m "feat(sleep): extract ScheduleCard (F2)"
```

---

### Task 9: `WolCard.tsx`

**Files:**
- Create: `client/src/components/power/sleep-config/WolCard.tsx`
- Test: `client/src/__tests__/components/power/sleep-config/WolCard.test.tsx`

**Interfaces:**
- Consumes: `SleepConfigForm`; `SleepCapabilities` from `../../../api/sleep`; `Wifi` icon.
- Produces: `WolCard(props: Pick<SleepConfigForm, 'wolMac'|'wolBroadcast'> & { update: (patch: Partial<SleepConfigForm>) => void; capabilities: SleepCapabilities | null })`.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/power/sleep-config/WolCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WolCard } from '../../../../components/power/sleep-config/WolCard';
import type { SleepCapabilities } from '../../../../api/sleep';

const caps = (own: string | null): SleepCapabilities => ({
  hdparm_available: true, rtcwake_available: true, systemctl_available: true,
  can_suspend: true, wol_interfaces: [], data_disk_devices: [], own_mac_address: own,
});

const base = { wolMac: '', wolBroadcast: '', update: vi.fn(), capabilities: caps(null) };

describe('WolCard', () => {
  it('renders the two address inputs', () => {
    render(<WolCard {...base} />);
    expect(screen.getByText('MAC Address')).toBeInTheDocument();
    expect(screen.getByText('Broadcast Address')).toBeInTheDocument();
  });

  it('offers the detected MAC when it differs from the current value', () => {
    const update = vi.fn();
    render(<WolCard {...base} capabilities={caps('DE:AD:BE:EF:00:01')} update={update} />);
    // accessible name spans split text nodes ("Erkannt: <mac> — Übernehmen?"); match by role+name regex
    fireEvent.click(screen.getByRole('button', { name: /Übernehmen/ }));
    expect(update).toHaveBeenCalledWith({ wolMac: 'DE:AD:BE:EF:00:01' });
  });

  it('does not offer the detected MAC when it already matches', () => {
    render(<WolCard {...base} wolMac="DE:AD:BE:EF:00:01" capabilities={caps('DE:AD:BE:EF:00:01')} />);
    expect(screen.queryByRole('button', { name: /Übernehmen/ })).toBeNull();
  });

  it('editing the MAC input calls update', () => {
    const update = vi.fn();
    render(<WolCard {...base} update={update} />);
    fireEvent.change(screen.getByPlaceholderText('AA:BB:CC:DD:EE:FF'), { target: { value: '01:02:03:04:05:06' } });
    expect(update).toHaveBeenCalledWith({ wolMac: '01:02:03:04:05:06' });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/WolCard.test.tsx`
Expected: FAIL — cannot find module.

- [ ] **Step 3: Write the implementation (verbatim from panel lines 368–405)**

```tsx
// client/src/components/power/sleep-config/WolCard.tsx
import { Wifi } from 'lucide-react';
import type { SleepConfigForm } from '../../../hooks/useSleepConfigForm';
import type { SleepCapabilities } from '../../../api/sleep';

type WolCardProps = Pick<SleepConfigForm, 'wolMac' | 'wolBroadcast'> & {
  update: (patch: Partial<SleepConfigForm>) => void;
  capabilities: SleepCapabilities | null;
};

export function WolCard({ wolMac, wolBroadcast, update, capabilities }: WolCardProps) {
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-3">
      <h4 className="text-sm font-medium text-white flex items-center gap-2">
        <Wifi className="h-4 w-4 text-amber-400" />
        Wake-on-LAN
      </h4>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">MAC Address</label>
          <input
            type="text"
            value={wolMac}
            onChange={(e) => update({ wolMac: e.target.value })}
            placeholder="AA:BB:CC:DD:EE:FF"
            className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
          />
          {capabilities?.own_mac_address && capabilities.own_mac_address !== wolMac && (
            <button
              type="button"
              onClick={() => update({ wolMac: capabilities.own_mac_address! })}
              className="mt-1.5 text-xs text-teal-400 hover:text-teal-300 transition-colors"
            >
              Erkannt: <span className="font-mono">{capabilities.own_mac_address}</span> — Übernehmen?
            </button>
          )}
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Broadcast Address</label>
          <input
            type="text"
            value={wolBroadcast}
            onChange={(e) => update({ wolBroadcast: e.target.value })}
            placeholder="255.255.255.255"
            className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
          />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/WolCard.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/sleep-config/WolCard.tsx client/src/__tests__/components/power/sleep-config/WolCard.test.tsx
git commit -m "feat(sleep): extract WolCard (F2)"
```

---

### Task 10: `FritzBoxCard.tsx`

**Files:**
- Create: `client/src/components/power/sleep-config/FritzBoxCard.tsx`
- Test: `client/src/__tests__/components/power/sleep-config/FritzBoxCard.test.tsx`

**Interfaces:**
- Consumes: `Toggle` from `./SleepFormControls`; `FritzBoxForm` from `../../../hooks/useFritzBoxForm`; `FritzBoxConfig`, `SleepCapabilities` from api; `Router` icon.
- Produces: `FritzBoxCard(props: FritzBoxForm & { update: (patch: Partial<FritzBoxForm>) => void; config: FritzBoxConfig | null; testing: boolean; onTest: () => void; capabilities: SleepCapabilities | null })`.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/power/sleep-config/FritzBoxCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FritzBoxCard } from '../../../../components/power/sleep-config/FritzBoxCard';
import type { SleepCapabilities } from '../../../../api/sleep';

const caps: SleepCapabilities = {
  hdparm_available: true, rtcwake_available: true, systemctl_available: true,
  can_suspend: true, wol_interfaces: [], data_disk_devices: [], own_mac_address: null,
};
const base = {
  host: '192.168.178.1', port: 49000, username: '', password: '', mac: '', enabled: false,
  update: vi.fn(), config: null, testing: false, onTest: vi.fn(), capabilities: caps,
};

describe('FritzBoxCard', () => {
  it('hides the detail fields when disabled', () => {
    render(<FritzBoxCard {...base} enabled={false} />);
    expect(screen.queryByText('Host')).toBeNull();
  });

  it('shows detail fields + test button when enabled and fires onTest', () => {
    const onTest = vi.fn();
    render(<FritzBoxCard {...base} enabled onTest={onTest} />);
    expect(screen.getByText('Host')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Test Connection'));
    expect(onTest).toHaveBeenCalled();
  });

  it('disables the test button while testing', () => {
    render(<FritzBoxCard {...base} enabled testing />);
    expect(screen.getByText('Testing...').closest('button')).toBeDisabled();
  });

  it('editing host calls update', () => {
    const update = vi.fn();
    render(<FritzBoxCard {...base} enabled update={update} />);
    fireEvent.change(screen.getByPlaceholderText('192.168.178.1'), { target: { value: '10.0.0.1' } });
    expect(update).toHaveBeenCalledWith({ host: '10.0.0.1' });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/FritzBoxCard.test.tsx`
Expected: FAIL — cannot find module.

- [ ] **Step 3: Write the implementation (verbatim from panel lines 407–493)**

```tsx
// client/src/components/power/sleep-config/FritzBoxCard.tsx
import { Router } from 'lucide-react';
import { Toggle } from './SleepFormControls';
import type { FritzBoxForm } from '../../../hooks/useFritzBoxForm';
import type { FritzBoxConfig } from '../../../api/fritzbox';
import type { SleepCapabilities } from '../../../api/sleep';

type FritzBoxCardProps = FritzBoxForm & {
  update: (patch: Partial<FritzBoxForm>) => void;
  config: FritzBoxConfig | null;
  testing: boolean;
  onTest: () => void;
  capabilities: SleepCapabilities | null;
};

export function FritzBoxCard({
  host, port, username, password, mac, enabled, update, config, testing, onTest, capabilities,
}: FritzBoxCardProps) {
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-3">
      <h4 className="text-sm font-medium text-white flex items-center gap-2">
        <Router className="h-4 w-4 text-orange-400" />
        Fritz!Box WoL
        <span className="ml-auto">
          <Toggle checked={enabled} onChange={(v) => update({ enabled: v })} />
        </span>
      </h4>
      {enabled && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Host</label>
              <input
                type="text"
                value={host}
                onChange={(e) => update({ host: e.target.value })}
                placeholder="192.168.178.1"
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Port</label>
              <input
                type="number"
                value={port}
                onChange={(e) => update({ port: Number(e.target.value) })}
                placeholder="49000"
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
              />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Username</label>
              <input
                type="text"
                value={username}
                onChange={(e) => update({ username: e.target.value })}
                placeholder="(often empty)"
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Password {config?.has_password && <span className="text-teal-400">(set)</span>}
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => update({ password: e.target.value })}
                placeholder={config?.has_password ? '••••••••' : 'TR-064 Password'}
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">NAS MAC Address</label>
            <input
              type="text"
              value={mac}
              onChange={(e) => update({ mac: e.target.value })}
              placeholder="AA:BB:CC:DD:EE:FF"
              className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
            />
            {capabilities?.own_mac_address && capabilities.own_mac_address !== mac && (
              <button
                type="button"
                onClick={() => update({ mac: capabilities.own_mac_address! })}
                className="mt-1.5 text-xs text-teal-400 hover:text-teal-300 transition-colors"
              >
                Erkannt: <span className="font-mono">{capabilities.own_mac_address}</span> — Übernehmen?
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={onTest}
            disabled={testing}
            className="rounded-lg bg-orange-500/20 px-4 py-2 text-sm font-medium text-orange-300 hover:bg-orange-500/30 transition-colors disabled:opacity-50"
          >
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/FritzBoxCard.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/sleep-config/FritzBoxCard.tsx client/src/__tests__/components/power/sleep-config/FritzBoxCard.test.tsx
git commit -m "feat(sleep): extract FritzBoxCard (F2)"
```

---

### Task 11: `SleepBehaviorCard.tsx`

**Files:**
- Create: `client/src/components/power/sleep-config/SleepBehaviorCard.tsx`
- Test: `client/src/__tests__/components/power/sleep-config/SleepBehaviorCard.test.tsx`

**Interfaces:**
- Consumes: `ToggleRow`, `NumberInput` from `./SleepFormControls`; `SleepConfigForm`; `Server`, `HardDrive` icons.
- Produces: `SleepBehaviorCard(props: Pick<SleepConfigForm, 'pauseMonitoring'|'pauseDiskIo'|'diskSpindown'|'reducedTelemetry'> & { update: (patch: Partial<SleepConfigForm>) => void })`.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/power/sleep-config/SleepBehaviorCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SleepBehaviorCard } from '../../../../components/power/sleep-config/SleepBehaviorCard';

const base = { pauseMonitoring: true, pauseDiskIo: true, diskSpindown: true, reducedTelemetry: 30, update: vi.fn() };

describe('SleepBehaviorCard', () => {
  it('renders the three toggle rows and the interval input', () => {
    render(<SleepBehaviorCard {...base} />);
    expect(screen.getByText('Pause monitoring')).toBeInTheDocument();
    expect(screen.getByText('Pause disk I/O monitor')).toBeInTheDocument();
    expect(screen.getByText('Spin down data disks')).toBeInTheDocument();
    expect(screen.getByText('Reduced telemetry interval (s)')).toBeInTheDocument();
  });

  it('toggling "Pause monitoring" calls update', () => {
    const update = vi.fn();
    render(<SleepBehaviorCard {...base} update={update} />);
    // first toggle row button
    fireEvent.click(screen.getAllByRole('button')[0]);
    expect(update).toHaveBeenCalledWith({ pauseMonitoring: false });
  });

  it('editing the interval calls update', () => {
    const update = vi.fn();
    render(<SleepBehaviorCard {...base} update={update} />);
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '60' } });
    expect(update).toHaveBeenCalledWith({ reducedTelemetry: 60 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/SleepBehaviorCard.test.tsx`
Expected: FAIL — cannot find module.

- [ ] **Step 3: Write the implementation (verbatim from panel lines 495–518)**

```tsx
// client/src/components/power/sleep-config/SleepBehaviorCard.tsx
import { Server, HardDrive } from 'lucide-react';
import { ToggleRow, NumberInput } from './SleepFormControls';
import type { SleepConfigForm } from '../../../hooks/useSleepConfigForm';

type SleepBehaviorCardProps = Pick<
  SleepConfigForm,
  'pauseMonitoring' | 'pauseDiskIo' | 'diskSpindown' | 'reducedTelemetry'
> & { update: (patch: Partial<SleepConfigForm>) => void };

export function SleepBehaviorCard({ pauseMonitoring, pauseDiskIo, diskSpindown, reducedTelemetry, update }: SleepBehaviorCardProps) {
  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-3">
      <h4 className="text-sm font-medium text-white flex items-center gap-2">
        <Server className="h-4 w-4 text-teal-400" />
        Sleep Behavior
      </h4>
      <div className="space-y-3">
        <ToggleRow label="Pause monitoring" checked={pauseMonitoring} onChange={(v) => update({ pauseMonitoring: v })} />
        <ToggleRow label="Pause disk I/O monitor" checked={pauseDiskIo} onChange={(v) => update({ pauseDiskIo: v })} />
        <ToggleRow
          label="Spin down data disks"
          checked={diskSpindown}
          onChange={(v) => update({ diskSpindown: v })}
          icon={<HardDrive className="h-3.5 w-3.5 text-slate-400" />}
        />
        <NumberInput
          label="Reduced telemetry interval (s)"
          value={reducedTelemetry}
          onChange={(v) => update({ reducedTelemetry: v })}
          min={5}
          max={300}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/power/sleep-config/SleepBehaviorCard.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/sleep-config/SleepBehaviorCard.tsx client/src/__tests__/components/power/sleep-config/SleepBehaviorCard.test.tsx
git commit -m "feat(sleep): extract SleepBehaviorCard (F2)"
```

---

### Task 12: Barrel + rewire `SleepConfigPanel.tsx` + docs + full verify

**Files:**
- Create: `client/src/components/power/sleep-config/index.ts`
- Modify: `client/src/components/power/SleepConfigPanel.tsx` (full rewrite to orchestrator)
- Modify: `client/src/components/CLAUDE.md` (power-row note)
- Modify: `client/src/hooks/CLAUDE.md` (two new form hooks)

**Interfaces:**
- Consumes: all Task 1–11 exports.

- [ ] **Step 1: Create the barrel**

```ts
// client/src/components/power/sleep-config/index.ts
export { CapabilitiesCard } from './CapabilitiesCard';
export { IdleDetectionCard } from './IdleDetectionCard';
export { EscalationCard } from './EscalationCard';
export { PresenceCard } from './PresenceCard';
export { ScheduleCard } from './ScheduleCard';
export { WolCard } from './WolCard';
export { FritzBoxCard } from './FritzBoxCard';
export { SleepBehaviorCard } from './SleepBehaviorCard';
export { Toggle, ToggleRow, NumberInput } from './SleepFormControls';
```

- [ ] **Step 2: Rewrite `SleepConfigPanel.tsx`**

Replace the ENTIRE file with:

```tsx
/**
 * Sleep Config Panel - Configuration for sleep mode.
 *
 * Orchestrates auto-idle detection, escalation, presence, schedule, WoL,
 * Fritz!Box, and sleep-behavior settings. Form state is consolidated in
 * useSleepConfigForm / useFritzBoxForm; each section is a card in ./sleep-config.
 */

import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import {
  getSleepConfig,
  getSleepStatus,
  updateSleepConfig,
  getSleepCapabilities,
  type SleepCapabilities,
  type PresenceStatus,
} from '../../api/sleep';
import { getFritzBoxConfig, updateFritzBoxConfig } from '../../api/fritzbox';
import { useSleepConfigForm } from '../../hooks/useSleepConfigForm';
import { useFritzBoxForm } from '../../hooks/useFritzBoxForm';
import {
  CapabilitiesCard,
  IdleDetectionCard,
  EscalationCard,
  PresenceCard,
  ScheduleCard,
  WolCard,
  FritzBoxCard,
  SleepBehaviorCard,
} from './sleep-config';

export function SleepConfigPanel() {
  const [capabilities, setCapabilities] = useState<SleepCapabilities | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [coreUptimeMasterOn, setCoreUptimeMasterOn] = useState(false);
  const [alwaysAwakeOn, setAlwaysAwakeOn] = useState(false);
  const [presenceStatus, setPresenceStatus] = useState<PresenceStatus | null>(null);

  const sleepForm = useSleepConfigForm();
  const fbForm = useFritzBoxForm();

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [configData, caps] = await Promise.all([
        getSleepConfig(),
        getSleepCapabilities(),
      ]);
      setCapabilities(caps);
      sleepForm.syncFromResponse(configData);

      try {
        const fb = await getFritzBoxConfig();
        fbForm.syncFromConfig(fb);
      } catch {
        // Fritz!Box config not available yet — ignore
      }
      try {
        const st = await getSleepStatus();
        setCoreUptimeMasterOn(st.core_uptime?.enabled ?? false);
        setAlwaysAwakeOn(st.always_awake?.enabled ?? false);
        setPresenceStatus(st.presence ?? null);
      } catch {
        // ignore — status is best-effort here
      }
    } catch {
      toast.error('Failed to load sleep config');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await updateSleepConfig(sleepForm.toPayload());

      try {
        await updateFritzBoxConfig(fbForm.toPayload());
      } catch {
        toast.error('Failed to save Fritz!Box config');
      }

      toast.success('Sleep configuration saved');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save config');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="card border-slate-700/50 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-700/50 rounded w-1/3" />
          <div className="h-40 bg-slate-700/50 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {capabilities && (
        <CapabilitiesCard capabilities={capabilities} helpOpen={helpOpen} onToggleHelp={() => setHelpOpen(!helpOpen)} />
      )}

      <IdleDetectionCard {...sleepForm.form} update={sleepForm.update} />
      <EscalationCard {...sleepForm.form} update={sleepForm.update} />
      <PresenceCard {...sleepForm.form} update={sleepForm.update} presenceStatus={presenceStatus} />
      <ScheduleCard {...sleepForm.form} update={sleepForm.update} coreUptimeMasterOn={coreUptimeMasterOn} alwaysAwakeOn={alwaysAwakeOn} />
      <WolCard {...sleepForm.form} update={sleepForm.update} capabilities={capabilities} />
      <FritzBoxCard {...fbForm.form} update={fbForm.update} config={fbForm.config} testing={fbForm.testing} onTest={fbForm.test} capabilities={capabilities} />
      <SleepBehaviorCard {...sleepForm.form} update={sleepForm.update} />

      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={busy}
          className="rounded-lg bg-teal-500/20 px-6 py-2.5 text-sm font-medium text-teal-300 hover:bg-teal-500/30 transition-colors disabled:opacity-50"
        >
          {busy ? 'Saving...' : 'Save Configuration'}
        </button>
      </div>
    </div>
  );
}
```

> Note: the `{...sleepForm.form}` spread passes every form field; each card's props are a `Pick` subset — JSX spread does not trigger excess-property errors, so this is type-safe. The cards read only their own fields.

- [ ] **Step 3: Verify the panel shrank**

Run: `cd client && node -e "console.log(require('fs').readFileSync('src/components/power/SleepConfigPanel.tsx','utf8').split(/\r?\n/).length)"`
Expected: a number **< 200** (target ~150).

- [ ] **Step 4: Type-check + lint + full unit suite**

Run: `cd client && npx eslint . ; npm run build ; npx vitest run`
Expected: eslint 0 errors; `npm run build` (tsc -b + vite) success; vitest all green (new sleep-config tests + existing suite).

> If `eslint` flags `react-hooks/exhaustive-deps` on the `useEffect(() => { loadData() }, [])`, note the original panel had the identical pattern and passed CI (the rule is relaxed repo-wide, #244) — leave it as-is. Only fix genuine unused-import errors.

- [ ] **Step 5: Update docs**

In `client/src/components/CLAUDE.md`, extend the `power/` row to mention the sleep-config decomposition, e.g. append:
`SleepConfigPanel composes ./sleep-config/* (8 section cards + SleepFormControls), form state in useSleepConfigForm/useFritzBoxForm (extracted F2)`

In `client/src/hooks/CLAUDE.md`, add two rows to the Utility/Data table:
`| useSleepConfigForm.ts | — | Consolidates SleepConfigPanel's 20 sleep-config form fields into one object + update/syncFromResponse/toPayload (SleepConfigUpdate). No TanStack (user-triggered config). |`
`| useFritzBoxForm.ts | api/fritzbox | Fritz!Box form object + config + toPayload (password only if set, mac||undefined) + test() (connection test + toast). No TanStack. |`

- [ ] **Step 6: Commit**

```bash
git add client/src/components/power/sleep-config/index.ts client/src/components/power/SleepConfigPanel.tsx client/src/components/CLAUDE.md client/src/hooks/CLAUDE.md
git commit -m "refactor(sleep): compose SleepConfigPanel from sleep-config/* + form hooks, panel under 200 (F2)"
```

---

### Task 13: `SleepConfigPanel.test.tsx` (integration)

**Files:**
- Create: `client/src/__tests__/components/power/SleepConfigPanel.test.tsx`

**Interfaces:**
- Consumes: the rewired panel + all pieces (integration).

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/components/power/SleepConfigPanel.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../../api/sleep', () => ({
  getSleepConfig: vi.fn(),
  getSleepCapabilities: vi.fn(),
  getSleepStatus: vi.fn(),
  updateSleepConfig: vi.fn(),
}));
vi.mock('../../../api/fritzbox', () => ({
  getFritzBoxConfig: vi.fn(),
  updateFritzBoxConfig: vi.fn(),
  testFritzBoxConnection: vi.fn(),
}));

import { getSleepConfig, getSleepCapabilities, getSleepStatus, updateSleepConfig } from '../../../api/sleep';
import { getFritzBoxConfig, updateFritzBoxConfig } from '../../../api/fritzbox';
import type { SleepConfigResponse, SleepCapabilities } from '../../../api/sleep';
import { SleepConfigPanel } from '../../../components/power/SleepConfigPanel';

const config: SleepConfigResponse = {
  auto_idle_enabled: true, idle_timeout_minutes: 15, idle_cpu_threshold: 5,
  idle_disk_io_threshold: 0.5, idle_http_threshold: 5,
  auto_escalation_enabled: false, escalation_after_minutes: 60,
  schedule_enabled: false, schedule_sleep_time: '23:00', schedule_wake_time: '06:00',
  schedule_mode: 'soft', wol_mac_address: null, wol_broadcast_address: null,
  pause_monitoring: true, pause_disk_io: true, reduced_telemetry_interval: 30,
  disk_spindown_enabled: true, core_uptime_enabled: false, core_uptime_suspend_on_exit: false,
  presence_enabled: true, presence_mode: 'active', presence_timeout_minutes: 3,
};
const caps: SleepCapabilities = {
  hdparm_available: true, rtcwake_available: true, systemctl_available: true,
  can_suspend: true, wol_interfaces: ['eth0'], data_disk_devices: ['sda'], own_mac_address: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  (getSleepConfig as any).mockResolvedValue(config);
  (getSleepCapabilities as any).mockResolvedValue(caps);
  (getSleepStatus as any).mockResolvedValue({ core_uptime: { enabled: false }, always_awake: { enabled: false }, presence: null });
  (getFritzBoxConfig as any).mockResolvedValue({ host: '192.168.178.1', port: 49000, username: '', nas_mac_address: null, enabled: false, has_password: false });
  (updateSleepConfig as any).mockResolvedValue(config);
  (updateFritzBoxConfig as any).mockResolvedValue(undefined);
});

describe('SleepConfigPanel (integration)', () => {
  it('loads config, seeds the form, and saves the edited payload', async () => {
    render(<SleepConfigPanel />);

    // after load: capabilities card + save button visible
    await waitFor(() => expect(screen.getByText('System Capabilities')).toBeInTheDocument());
    expect(screen.getByText('Save Configuration')).toBeInTheDocument();

    // idle detection was seeded enabled -> its inputs are visible; edit the timeout
    const timeout = screen.getAllByRole('spinbutton')[0];
    fireEvent.change(timeout, { target: { value: '25' } });

    fireEvent.click(screen.getByText('Save Configuration'));

    await waitFor(() => expect(updateSleepConfig).toHaveBeenCalledTimes(1));
    const payload = (updateSleepConfig as any).mock.calls[0][0];
    expect(payload.idle_timeout_minutes).toBe(25);
    expect(payload.wol_mac_address).toBeNull();          // empty -> null mapping preserved
    expect(payload.presence_mode).toBe('active');
    expect(updateFritzBoxConfig).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails, then passes**

Run: `cd client && npx vitest run src/__tests__/components/power/SleepConfigPanel.test.tsx`
Expected: PASS. If a mock-wiring detail needs adjusting (e.g. the first `spinbutton` is not the idle timeout because another enabled section renders a number input above it), adjust ONLY the selector to target the idle-timeout input (e.g. `screen.getByRole('spinbutton', { name: ... })` is not available since labels aren't associated — instead assert on the number of `updateSleepConfig` call and the specific field). Do NOT weaken the payload assertions and do NOT change any source file. If the panel's actual behavior contradicts an assertion, STOP and report BLOCKED.

> Selector note: with the seed above, `auto_idle_enabled` is true (idle inputs shown) and escalation/schedule are off, so the FIRST `spinbutton` on the page is the idle timeout. If that ordering is off, target it via `within(screen.getByText('Auto-Idle Detection').closest('div.card')!)` and `getAllByRole('spinbutton')[0]`.

- [ ] **Step 3: Lint the new test + full suite**

Run: `cd client && npx eslint src/__tests__/components/power/SleepConfigPanel.test.tsx ; npx vitest run`
Expected: eslint 0 errors (any `as any` mock casts are pre-existing-pattern warnings, acceptable); vitest fully green.

- [ ] **Step 4: Commit**

```bash
git add client/src/__tests__/components/power/SleepConfigPanel.test.tsx
git commit -m "test(sleep): panel integration test — load seeds form, save sends edited payload (F2)"
```

---

## Manual Verification (after Task 13)

Start dev (`python start_dev.py`), open the Sleep page (`/sleep`), the config panel:

- [ ] Alle 8 Sektionen rendern; Capabilities-Badges + Setup-Help-Akkordeon.
- [ ] Toggles/Inputs schreiben; conditional-Sektionen (Idle/Escalation/Presence/Schedule/FritzBox) klappen bei Toggle auf/zu.
- [ ] Schedule-Override-Banner erscheint bei aktivem Core-Uptime/Always-Awake.
- [ ] WoL/FritzBox „Erkannt: … Übernehmen?"-Button (falls `own_mac_address` gesetzt).
- [ ] Save persistiert (Payload unverändert); Reload zeigt die gespeicherten Werte.
- [ ] Fritz!Box „Test Connection" toastet.

---

## Self-Review Notes (author)

- **Spec coverage:** 2 Form-Hooks (T2/T3) + Primitives (T1) + CapabilitiesCard (T4) + 6 weitere Cards (T5–T11) + Barrel/Panel/Docs (T12) + Panel-Integration (T13). Alle Spec-Punkte gemappt. ✓
- **Type consistency:** `SleepConfigForm` (T2) wird von jeder Card als `Pick<…>`-Prop konsumiert; `update: (patch: Partial<SleepConfigForm>) => void` überall identisch. `FritzBoxForm` (T3) von FritzBoxCard (T10). Panel (T12) spreizt `{...form}` in die `Pick`-Props (JSX-Spread → keine Excess-Prop-Fehler). ✓
- **Behavior:** `toPayload` (T2) reproduziert das aktuelle `handleSave`-Objekt feldgenau inkl. `wolMac || null`; FB-`toPayload` (T3) inkl. `password`-nur-wenn-gesetzt + `mac || undefined`. loadData/handleSave (T12) verbatim inkl. best-effort try/catch + unified Toast. ✓
- **i18n:** nur die bestehenden `t('sleep.…')`-Keys wandern in PresenceCard/ScheduleCard (`useTranslation('system')`); hardcodierte Strings verbatim. ✓
- **Field names verified** gegen `api/sleep.ts` + `api/fritzbox.ts` (SleepConfigResponse/Update 20-Feld-Mapping, FritzBoxConfig/Update). Falls ein Feld zur Implementierungszeit abweicht, dem echten `api/*.ts`-Typ folgen.
