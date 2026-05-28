# Topbar Status Strip — Phase 2: Frontend Strip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the live status strip in the desktop topbar — a typed API client, a `<Pill>` primitive, a native polling hook, a per-second Always-Awake countdown, and the `<TopbarStatusStrip>` container wired into `Layout.tsx`.

**Architecture:** `<TopbarStatusStrip>` polls `GET /api/system/statusbar/state` every 10s (native `setInterval`, paused when the tab is hidden), maps each returned `PillState` to a renderer (generic `<Pill>` for most, `<AlwaysAwakePill>` for the live countdown), and replaces the empty desktop spacer in the topbar. Read-only — each pill is a `<Link>`.

**Tech Stack:** React 18, TypeScript, Tailwind, react-router-dom v7 (`<Link>`), lucide-react (icons by string name), axios (`apiClient`), Vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-05-27-topbar-statusbar-design.md`

**Prerequisite:** Phase 1 (backend) merged — `GET /api/system/statusbar/state` returns `{ pills: PillState[], show_bottom_upload: boolean }`.

> **Spec correction (verified against `client/package.json`):** the project does **not** depend on `@tanstack/react-query`. The polling hook is built with native `useEffect` + `setInterval` + the Page Visibility API, not TanStack Query. The existing `client/src/components/ui/Badge.tsx` uses a different (gray/green/blue, light+dark) theme and is a non-clickable chip — we create a new `<Pill>` primitive rather than retrofit it.

**Verified patterns:**
- API module: `import { apiClient } from '../lib/api'`; `const BASE = '/api/...'`; `await apiClient.get<T>(BASE)` (`client/src/api/coreUptime.ts`).
- `isPi` from `client/src/lib/features.ts`; already imported in `Layout.tsx` (used at line 506).
- Topbar spacer to replace: `Layout.tsx:517` — `<div className="hidden lg:block flex-1" />`.
- Test pattern: `client/src/__tests__/components/...`, `vitest` + `@testing-library/react` (`render, screen, fireEvent, act`), `vi.mock('react-i18next', ...)` (`client/src/__tests__/components/quickSettings/ByteUnitSection.test.tsx`). Run with `cd client && npm run test`.
- Backend `PillState.icon` is a lucide icon name string (`"Zap"`, `"Shield"`, `"Upload"`, `"RefreshCw"`, `"HardDrive"`, `"Moon"`, `"Lock"`, `"Thermometer"`, `"Coffee"`, `"Clock"`, `"Save"`).

---

## File Structure

**Create:**
- `client/src/api/statusBar.ts` — typed client (`getStatusBarState`, `getStatusBarConfig`, `updateStatusBarConfig`) + TS types mirroring the backend schemas
- `client/src/components/ui/Pill.tsx` — generic tone-aware clickable pill
- `client/src/hooks/useCountdown.ts` — per-second countdown that re-anchors on input change
- `client/src/hooks/useStatusBarState.ts` — 10s polling hook with pause-when-hidden + last-known-state
- `client/src/components/topbar/iconMap.ts` — lucide icon name → component
- `client/src/components/topbar/pills/AlwaysAwakePill.tsx` — countdown pill
- `client/src/components/topbar/pillRenderers.tsx` — `PillRenderer` switch
- `client/src/components/topbar/TopbarStatusStrip.tsx` — container
- Tests under `client/src/__tests__/components/topbar/` and `client/src/__tests__/hooks/`

**Modify:**
- `client/src/components/Layout.tsx` — replace the line 517 spacer

---

## Task 1: Typed API client

**Files:**
- Create: `client/src/api/statusBar.ts`
- Test: `client/src/__tests__/api/statusBar.test.ts`

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/api/statusBar.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../../lib/api';
import { getStatusBarState, updateStatusBarConfig } from '../../api/statusBar';

vi.mock('../../lib/api', () => ({
  apiClient: { get: vi.fn(), put: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('statusBar api', () => {
  it('getStatusBarState calls the state endpoint and returns data', async () => {
    (apiClient.get as any).mockResolvedValue({ data: { pills: [], show_bottom_upload: true } });
    const result = await getStatusBarState();
    expect(apiClient.get).toHaveBeenCalledWith('/api/system/statusbar/state');
    expect(result.show_bottom_upload).toBe(true);
  });

  it('updateStatusBarConfig PUTs the payload', async () => {
    (apiClient.put as any).mockResolvedValue({ data: { pills: [], show_bottom_upload: false } });
    await updateStatusBarConfig({ pills: [], show_bottom_upload: false });
    expect(apiClient.put).toHaveBeenCalledWith('/api/system/statusbar/config', { pills: [], show_bottom_upload: false });
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd client && npm run test -- statusBar.test`
Expected: FAIL — cannot import `../../api/statusBar`.

- [ ] **Step 3: Create the client**

Create `client/src/api/statusBar.ts`:

```ts
/**
 * API client for the topbar status strip.
 */
import { apiClient } from '../lib/api';

export type PillId =
  | 'power' | 'pihole' | 'uploads' | 'sync' | 'raid' | 'sleep' | 'vpn' | 'temp'
  | 'always_awake' | 'scheduler' | 'backup';

export type PillTone = 'success' | 'info' | 'warning' | 'danger' | 'neutral';
export type PillKind = 'state' | 'activity' | 'alert';
export type PillVisibility = 'admin' | 'all';

export interface PillState {
  id: PillId;
  kind: PillKind;
  tone: PillTone;
  label: string;
  value?: string | null;
  icon?: string | null;
  href: string;
  extra?: Record<string, unknown> | null;
}

export interface StatusBarStateResponse {
  pills: PillState[];
  show_bottom_upload: boolean;
}

export interface PillCatalogEntry {
  pill_id: PillId;
  name_key: string;
  enabled: boolean;
  visibility: PillVisibility;
  visibility_locked: boolean;
  sort_order: number;
  href: string;
}

export interface StatusBarConfigResponse {
  pills: PillCatalogEntry[];
  show_bottom_upload: boolean;
}

export interface PillConfigItem {
  pill_id: PillId;
  enabled: boolean;
  visibility: PillVisibility;
  sort_order: number;
}

export interface StatusBarConfigUpdate {
  pills: PillConfigItem[];
  show_bottom_upload: boolean;
}

const STATE = '/api/system/statusbar/state';
const CONFIG = '/api/system/statusbar/config';

export async function getStatusBarState(): Promise<StatusBarStateResponse> {
  const r = await apiClient.get<StatusBarStateResponse>(STATE);
  return r.data;
}

export async function getStatusBarConfig(): Promise<StatusBarConfigResponse> {
  const r = await apiClient.get<StatusBarConfigResponse>(CONFIG);
  return r.data;
}

export async function updateStatusBarConfig(
  payload: StatusBarConfigUpdate,
): Promise<StatusBarConfigResponse> {
  const r = await apiClient.put<StatusBarConfigResponse>(CONFIG, payload);
  return r.data;
}
```

- [ ] **Step 4: Run — should pass**

Run: `cd client && npm run test -- statusBar.test`
Expected: PASS (2)

- [ ] **Step 5: Commit**

```bash
git add client/src/api/statusBar.ts client/src/__tests__/api/statusBar.test.ts
git commit -m "feat(statusbar): typed frontend API client"
```

---

## Task 2: `<Pill>` primitive

**Files:**
- Create: `client/src/components/ui/Pill.tsx`
- Test: `client/src/__tests__/components/ui/Pill.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/ui/Pill.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Pill } from '../../../components/ui/Pill';

function renderPill(props: Partial<React.ComponentProps<typeof Pill>> = {}) {
  return render(
    <MemoryRouter>
      <Pill tone="warning" label="RAID" value="degraded" href="/x" {...props} />
    </MemoryRouter>,
  );
}

describe('Pill', () => {
  it('renders label and value', () => {
    renderPill();
    expect(screen.getByText('RAID')).toBeInTheDocument();
    expect(screen.getByText('degraded')).toBeInTheDocument();
  });

  it('renders as a link to href', () => {
    renderPill({ href: '/admin/system-control?tab=raid' });
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/admin/system-control?tab=raid');
  });

  it('applies warning tone classes', () => {
    renderPill({ tone: 'warning' });
    const link = screen.getByRole('link');
    expect(link.className).toContain('amber');
  });

  it('sets an aria-label combining label and value', () => {
    renderPill({ label: 'RAID', value: 'degraded' });
    expect(screen.getByLabelText('RAID: degraded')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd client && npm run test -- Pill.test`
Expected: FAIL — cannot import `Pill`.

- [ ] **Step 3: Create the primitive**

Create `client/src/components/ui/Pill.tsx`:

```tsx
import React from 'react';
import { Link } from 'react-router-dom';

export type PillTone = 'success' | 'info' | 'warning' | 'danger' | 'neutral';

export interface PillProps {
  tone: PillTone;
  label: string;
  value?: string | null;
  href: string;
  icon?: React.ReactNode;
  ariaLabel?: string;
}

const TONE_CLASSES: Record<PillTone, string> = {
  success: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20',
  info: 'border-sky-500/40 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20',
  warning: 'border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20',
  danger: 'border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20',
  neutral: 'border-slate-700 bg-slate-800/60 text-slate-300 hover:bg-slate-800',
};

export function Pill({ tone, label, value, href, icon, ariaLabel }: PillProps) {
  const aria = ariaLabel ?? (value ? `${label}: ${value}` : label);
  return (
    <Link
      to={href}
      aria-label={aria}
      title={aria}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60 ${TONE_CLASSES[tone]}`}
    >
      {icon}
      <span>{label}</span>
      {value != null && value !== '' && <span className="opacity-80">{value}</span>}
    </Link>
  );
}
```

- [ ] **Step 4: Run — should pass**

Run: `cd client && npm run test -- Pill.test`
Expected: PASS (4)

- [ ] **Step 5: Commit**

```bash
git add client/src/components/ui/Pill.tsx client/src/__tests__/components/ui/Pill.test.tsx
git commit -m "feat(statusbar): tone-aware Pill primitive"
```

---

## Task 3: `useCountdown` hook

**Files:**
- Create: `client/src/hooks/useCountdown.ts`
- Test: `client/src/__tests__/hooks/useCountdown.test.ts`

Returns a formatted countdown string that decrements once per second and re-anchors whenever the input `seconds` changes (i.e. when a new poll arrives).

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/hooks/useCountdown.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCountdown, formatCountdown } from '../../hooks/useCountdown';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('formatCountdown', () => {
  it('formats < 1h as MM:SS', () => {
    expect(formatCountdown(125)).toBe('02:05');
  });
  it('formats >= 1h as HH:MM:SS', () => {
    expect(formatCountdown(3661)).toBe('01:01:01');
  });
  it('clamps negatives to 00:00', () => {
    expect(formatCountdown(-5)).toBe('00:00');
  });
});

describe('useCountdown', () => {
  it('decrements once per second', () => {
    const { result } = renderHook(({ s }) => useCountdown(s), { initialProps: { s: 120 } });
    expect(result.current).toBe('02:00');
    act(() => { vi.advanceTimersByTime(5000); });
    expect(result.current).toBe('01:55');
  });

  it('re-anchors when seconds prop changes (new poll)', () => {
    const { result, rerender } = renderHook(({ s }) => useCountdown(s), { initialProps: { s: 120 } });
    act(() => { vi.advanceTimersByTime(3000); });
    expect(result.current).toBe('01:57');
    rerender({ s: 600 });   // new poll arrives
    expect(result.current).toBe('10:00');
  });

  it('returns null for null input', () => {
    const { result } = renderHook(() => useCountdown(null));
    expect(result.current).toBeNull();
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd client && npm run test -- useCountdown.test`
Expected: FAIL — cannot import `useCountdown`.

- [ ] **Step 3: Implement the hook**

Create `client/src/hooks/useCountdown.ts`:

```ts
import { useEffect, useRef, useState } from 'react';

export function formatCountdown(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

/**
 * Per-second countdown string. Re-anchors to `seconds` whenever it changes
 * (each poll supplies a fresh server value). Returns null when `seconds` is null.
 */
export function useCountdown(seconds: number | null): string | null {
  const [remaining, setRemaining] = useState<number | null>(seconds);
  const anchorRef = useRef<number | null>(seconds);

  // Re-anchor on input change.
  useEffect(() => {
    anchorRef.current = seconds;
    setRemaining(seconds);
  }, [seconds]);

  useEffect(() => {
    if (seconds == null) return;
    const id = setInterval(() => {
      setRemaining((prev) => (prev == null ? null : Math.max(0, prev - 1)));
    }, 1000);
    return () => clearInterval(id);
  }, [seconds]);

  return remaining == null ? null : formatCountdown(remaining);
}
```

- [ ] **Step 4: Run — should pass**

Run: `cd client && npm run test -- useCountdown.test`
Expected: PASS (6)

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useCountdown.ts client/src/__tests__/hooks/useCountdown.test.ts
git commit -m "feat(statusbar): useCountdown hook with re-anchor"
```

---

## Task 4: `useStatusBarState` polling hook

**Files:**
- Create: `client/src/hooks/useStatusBarState.ts`
- Test: `client/src/__tests__/hooks/useStatusBarState.test.ts`

Polls every 10s, pauses while `document.hidden`, holds last-known state on error, clears after 3 consecutive failures.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/hooks/useStatusBarState.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

vi.mock('../../api/statusBar', () => ({
  getStatusBarState: vi.fn(),
}));

import { getStatusBarState } from '../../api/statusBar';
import { useStatusBarState } from '../../hooks/useStatusBarState';

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});
afterEach(() => vi.useRealTimers());

describe('useStatusBarState', () => {
  it('fetches once on mount and exposes pills', async () => {
    (getStatusBarState as any).mockResolvedValue({
      pills: [{ id: 'power', kind: 'state', tone: 'info', label: 'P', href: '/x' }],
      show_bottom_upload: true,
    });
    const { result } = renderHook(() => useStatusBarState());
    await act(async () => { await Promise.resolve(); });
    expect(result.current.state?.pills).toHaveLength(1);
  });

  it('holds last-known state on a single error', async () => {
    (getStatusBarState as any)
      .mockResolvedValueOnce({ pills: [{ id: 'power', kind: 'state', tone: 'info', label: 'P', href: '/x' }], show_bottom_upload: true })
      .mockRejectedValueOnce(new Error('net'));
    const { result } = renderHook(() => useStatusBarState());
    await act(async () => { await Promise.resolve(); });
    await act(async () => { vi.advanceTimersByTime(10000); await Promise.resolve(); });
    // Still shows the last good payload after one failure
    expect(result.current.state?.pills).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd client && npm run test -- useStatusBarState.test`
Expected: FAIL — cannot import `useStatusBarState`.

- [ ] **Step 3: Implement the hook**

Create `client/src/hooks/useStatusBarState.ts`:

```ts
import { useEffect, useRef, useState } from 'react';
import { getStatusBarState, StatusBarStateResponse } from '../api/statusBar';

const POLL_MS = 10_000;
const MAX_FAILURES = 3;

export interface UseStatusBarState {
  state: StatusBarStateResponse | null;
  stale: boolean;
}

export function useStatusBarState(): UseStatusBarState {
  const [state, setState] = useState<StatusBarStateResponse | null>(null);
  const [stale, setStale] = useState(false);
  const failuresRef = useRef(0);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      if (document.hidden) return; // pause when tab not visible
      try {
        const data = await getStatusBarState();
        if (cancelled) return;
        failuresRef.current = 0;
        setState(data);
        setStale(false);
      } catch {
        if (cancelled) return;
        failuresRef.current += 1;
        if (failuresRef.current >= MAX_FAILURES) {
          setState(null);
        } else {
          setStale(true); // keep last-known state, flag stale
        }
      }
    }

    poll(); // initial fetch
    const id = setInterval(poll, POLL_MS);
    const onVisible = () => { if (!document.hidden) poll(); };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      cancelled = true;
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  return { state, stale };
}
```

- [ ] **Step 4: Run — should pass**

Run: `cd client && npm run test -- useStatusBarState.test`
Expected: PASS (2)

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useStatusBarState.ts client/src/__tests__/hooks/useStatusBarState.test.ts
git commit -m "feat(statusbar): native polling hook with pause-when-hidden"
```

---

## Task 5: Icon map

**Files:**
- Create: `client/src/components/topbar/iconMap.ts`
- Test: `client/src/__tests__/components/topbar/iconMap.test.ts`

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/topbar/iconMap.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { resolveIcon } from '../../../components/topbar/iconMap';

describe('resolveIcon', () => {
  it('returns a component for a known icon name', () => {
    expect(resolveIcon('Zap')).toBeTruthy();
  });
  it('returns null for unknown / null', () => {
    expect(resolveIcon(null)).toBeNull();
    expect(resolveIcon('NotAnIcon')).toBeNull();
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd client && npm run test -- iconMap.test`
Expected: FAIL — cannot import `resolveIcon`.

- [ ] **Step 3: Implement**

Create `client/src/components/topbar/iconMap.ts`:

```ts
import {
  Zap, Shield, Upload, RefreshCw, HardDrive, Moon, Lock, Thermometer,
  Coffee, Clock, Save, LucideIcon,
} from 'lucide-react';

const ICONS: Record<string, LucideIcon> = {
  Zap, Shield, Upload, RefreshCw, HardDrive, Moon, Lock, Thermometer, Coffee, Clock, Save,
};

export function resolveIcon(name: string | null | undefined): LucideIcon | null {
  if (!name) return null;
  return ICONS[name] ?? null;
}
```

- [ ] **Step 4: Run — should pass**

Run: `cd client && npm run test -- iconMap.test`
Expected: PASS (2)

- [ ] **Step 5: Commit**

```bash
git add client/src/components/topbar/iconMap.ts client/src/__tests__/components/topbar/iconMap.test.ts
git commit -m "feat(statusbar): lucide icon-name resolver"
```

---

## Task 6: Always-Awake pill (live countdown)

**Files:**
- Create: `client/src/components/topbar/pills/AlwaysAwakePill.tsx`
- Test: `client/src/__tests__/components/topbar/AlwaysAwakePill.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/topbar/AlwaysAwakePill.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AlwaysAwakePill } from '../../../components/topbar/pills/AlwaysAwakePill';
import type { PillState } from '../../../api/statusBar';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function base(extra: Record<string, unknown> | null, value: string): PillState {
  return { id: 'always_awake', kind: 'state', tone: 'warning', label: 'Always Awake',
           value, href: '/admin/system-control?tab=sleep', icon: 'Coffee', extra };
}

function renderPill(pill: PillState) {
  return render(<MemoryRouter><AlwaysAwakePill pill={pill} /></MemoryRouter>);
}

describe('AlwaysAwakePill', () => {
  it('renders permanent label when no expiry', () => {
    renderPill(base(null, 'permanent'));
    expect(screen.getByText('permanent')).toBeInTheDocument();
  });

  it('counts down from extra.expires_in_seconds', () => {
    renderPill(base({ expires_in_seconds: 120 }, '02:00'));
    expect(screen.getByText('02:00')).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(5000); });
    expect(screen.getByText('01:55')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd client && npm run test -- AlwaysAwakePill.test`
Expected: FAIL — cannot import `AlwaysAwakePill`.

- [ ] **Step 3: Implement**

Create `client/src/components/topbar/pills/AlwaysAwakePill.tsx`:

```tsx
import React from 'react';
import { Pill } from '../../ui/Pill';
import { useCountdown } from '../../../hooks/useCountdown';
import { resolveIcon } from '../iconMap';
import type { PillState } from '../../../api/statusBar';

export function AlwaysAwakePill({ pill }: { pill: PillState }) {
  const expires = typeof pill.extra?.expires_in_seconds === 'number'
    ? (pill.extra!.expires_in_seconds as number)
    : null;
  const countdown = useCountdown(expires);
  const value = countdown ?? pill.value ?? undefined;

  const Icon = resolveIcon(pill.icon);
  return (
    <Pill
      tone={pill.tone}
      label={pill.label}
      value={value}
      href={pill.href}
      icon={Icon ? <Icon className="h-3.5 w-3.5" /> : undefined}
    />
  );
}
```

- [ ] **Step 4: Run — should pass**

Run: `cd client && npm run test -- AlwaysAwakePill.test`
Expected: PASS (2)

- [ ] **Step 5: Commit**

```bash
git add client/src/components/topbar/pills/AlwaysAwakePill.tsx client/src/__tests__/components/topbar/AlwaysAwakePill.test.tsx
git commit -m "feat(statusbar): always-awake pill with live countdown"
```

---

## Task 7: Pill renderer switch

**Files:**
- Create: `client/src/components/topbar/pillRenderers.tsx`
- Test: `client/src/__tests__/components/topbar/pillRenderers.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/topbar/pillRenderers.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PillRenderer } from '../../../components/topbar/pillRenderers';
import type { PillState } from '../../../api/statusBar';

function renderPill(pill: PillState) {
  return render(<MemoryRouter><PillRenderer pill={pill} /></MemoryRouter>);
}

describe('PillRenderer', () => {
  it('renders a generic pill for a normal pill', () => {
    renderPill({ id: 'raid', kind: 'alert', tone: 'warning', label: 'RAID',
                 value: 'degraded', href: '/x', icon: 'HardDrive', extra: null });
    expect(screen.getByText('RAID')).toBeInTheDocument();
    expect(screen.getByText('degraded')).toBeInTheDocument();
  });

  it('routes always_awake to the countdown pill', () => {
    renderPill({ id: 'always_awake', kind: 'state', tone: 'warning', label: 'Always Awake',
                 value: '02:00', href: '/x', icon: 'Coffee', extra: { expires_in_seconds: 120 } });
    expect(screen.getByText('Always Awake')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd client && npm run test -- pillRenderers.test`
Expected: FAIL — cannot import `PillRenderer`.

- [ ] **Step 3: Implement**

Create `client/src/components/topbar/pillRenderers.tsx`:

```tsx
import React from 'react';
import { Pill } from '../ui/Pill';
import { AlwaysAwakePill } from './pills/AlwaysAwakePill';
import { resolveIcon } from './iconMap';
import type { PillState } from '../../api/statusBar';

export function PillRenderer({ pill }: { pill: PillState }) {
  if (pill.id === 'always_awake') {
    return <AlwaysAwakePill pill={pill} />;
  }
  const Icon = resolveIcon(pill.icon);
  return (
    <Pill
      tone={pill.tone}
      label={pill.label}
      value={pill.value ?? undefined}
      href={pill.href}
      icon={Icon ? <Icon className="h-3.5 w-3.5" /> : undefined}
    />
  );
}
```

- [ ] **Step 4: Run — should pass**

Run: `cd client && npm run test -- pillRenderers.test`
Expected: PASS (2)

- [ ] **Step 5: Commit**

```bash
git add client/src/components/topbar/pillRenderers.tsx client/src/__tests__/components/topbar/pillRenderers.test.tsx
git commit -m "feat(statusbar): pill renderer switch"
```

---

## Task 8: `<TopbarStatusStrip>` container

**Files:**
- Create: `client/src/components/topbar/TopbarStatusStrip.tsx`
- Test: `client/src/__tests__/components/topbar/TopbarStatusStrip.test.tsx`

The container accepts an optional `previewState` (Phase 3 reuses this for the live preview). When `previewState` is provided it renders that and skips polling.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/topbar/TopbarStatusStrip.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TopbarStatusStrip } from '../../../components/topbar/TopbarStatusStrip';
import type { StatusBarStateResponse } from '../../../api/statusBar';

vi.mock('../../../hooks/useStatusBarState', () => ({
  useStatusBarState: () => ({ state: null, stale: false }),
}));

function preview(pills: any[]): StatusBarStateResponse {
  return { pills, show_bottom_upload: true };
}

describe('TopbarStatusStrip', () => {
  it('renders nothing when there are no pills', () => {
    const { container } = render(
      <MemoryRouter><TopbarStatusStrip previewState={preview([])} /></MemoryRouter>,
    );
    expect(container.querySelectorAll('a')).toHaveLength(0);
  });

  it('renders pills in payload order', () => {
    const pills = [
      { id: 'pihole', kind: 'state', tone: 'success', label: 'Pi-hole', value: 'on', href: '/pihole', icon: 'Shield', extra: null },
      { id: 'power', kind: 'state', tone: 'info', label: 'Power', value: null, href: '/x', icon: 'Zap', extra: null },
    ];
    render(<MemoryRouter><TopbarStatusStrip previewState={preview(pills)} /></MemoryRouter>);
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveTextContent('Pi-hole');
    expect(links[1]).toHaveTextContent('Power');
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd client && npm run test -- TopbarStatusStrip.test`
Expected: FAIL — cannot import `TopbarStatusStrip`.

- [ ] **Step 3: Implement**

Create `client/src/components/topbar/TopbarStatusStrip.tsx`:

```tsx
import React from 'react';
import { useStatusBarState } from '../../hooks/useStatusBarState';
import { PillRenderer } from './pillRenderers';
import type { StatusBarStateResponse } from '../../api/statusBar';

interface Props {
  /** When provided, renders this state and skips polling (used by the config Live Preview). */
  previewState?: StatusBarStateResponse;
}

export function TopbarStatusStrip({ previewState }: Props) {
  const { state: polled } = useStatusBarState();
  const state = previewState ?? polled;
  const pills = state?.pills ?? [];

  if (pills.length === 0) return null;

  return (
    <div className="flex items-center gap-2">
      {pills.map((pill) => (
        <PillRenderer key={pill.id} pill={pill} />
      ))}
    </div>
  );
}
```

> Note: the hook still runs when `previewState` is given (hooks can't be called conditionally), but its result is ignored. That's harmless — the preview path is only used inside the admin config tab. If you want to fully avoid the network call in preview mode, gate the fetch in `useStatusBarState` behind an `enabled` flag and pass `enabled={!previewState}`. Not required for correctness.

- [ ] **Step 4: Run — should pass**

Run: `cd client && npm run test -- TopbarStatusStrip.test`
Expected: PASS (2)

- [ ] **Step 5: Commit**

```bash
git add client/src/components/topbar/TopbarStatusStrip.tsx client/src/__tests__/components/topbar/TopbarStatusStrip.test.tsx
git commit -m "feat(statusbar): TopbarStatusStrip container with preview support"
```

---

## Task 9: Wire the strip into the topbar

**Files:**
- Modify: `client/src/components/Layout.tsx`

- [ ] **Step 1: Add the import**

In `client/src/components/Layout.tsx`, add to the component imports near the top (alongside other component imports):

```tsx
import { TopbarStatusStrip } from './topbar/TopbarStatusStrip';
```

- [ ] **Step 2: Replace the spacer at line 517**

Replace this exact line:

```tsx
              {/* Spacer to push right section */}
              <div className="hidden lg:block flex-1" />
```

with:

```tsx
              {/* Status strip (desktop only, hidden in Pi mode) */}
              <div className="hidden lg:flex flex-1 items-center justify-center px-6">
                {!isPi && <TopbarStatusStrip />}
              </div>
```

(`isPi` is already in scope — it's used at line 506.)

- [ ] **Step 3: Type-check and build**

Run: `cd client && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 4: Manual verification (dev server)**

Run the dev environment (`python start_dev.py` from repo root) and log in as admin. Because no pills are enabled by default (Phase 1 seeds all disabled), the strip is empty — that's correct. To see it now: enable a couple of pills directly via API:

```bash
curl -X PUT http://localhost:3001/api/system/statusbar/config \
  -H "Authorization: Bearer <admin-token>" -H "Content-Type: application/json" \
  -d '{"pills":[{"pill_id":"power","enabled":true,"visibility":"all","sort_order":0},{"pill_id":"pihole","enabled":true,"visibility":"all","sort_order":1}],"show_bottom_upload":true}'
```

Reload the dashboard → confirm pills appear in the topbar center, are clickable, and navigate. Resize below `lg` → strip disappears. (Full admin UI to toggle pills comes in Phase 3.)

- [ ] **Step 5: Commit**

```bash
git add client/src/components/Layout.tsx
git commit -m "feat(statusbar): mount TopbarStatusStrip in the desktop topbar"
```

---

## Task 10: Phase 2 verification

**Files:** none (verification only)

- [ ] **Step 1: Run all status-bar frontend tests**

Run: `cd client && npm run test -- statusBar Pill useCountdown useStatusBarState iconMap AlwaysAwakePill pillRenderers TopbarStatusStrip`
Expected: ALL PASS.

- [ ] **Step 2: Full type-check / build**

Run: `cd client && npm run build`
Expected: success.

- [ ] **Step 3: Lint**

Run: `cd client && npm run lint`
Expected: no new errors in the files created by this phase.

- [ ] **Step 4: Final commit (if fixes were needed)**

```bash
git add -A
git commit -m "test(statusbar): frontend strip phase 2 green"
```

---

## Self-Review (completed during planning)

**Spec coverage:**
- `<Pill>` primitive with tone classes → Task 2 ✓
- Polling every 10s, pause when hidden, last-known on failure → Task 4 ✓ (native, not TanStack — spec correction noted)
- Per-second Always-Awake countdown, re-anchor on poll → Tasks 3 + 6 ✓
- Hidden < lg + in Pi mode → Task 9 (`hidden lg:flex` + `!isPi`) ✓
- Read-only click-through (`<Link>`) → Task 2 ✓
- Renders pills in server order → Task 8 ✓
- Empty when no pills → Task 8 ✓
- Preview-state prop (consumed by Phase 3) → Task 8 ✓
- Icon-by-name from backend → Task 5 ✓

**Spec corrections folded in:**
- No `@tanstack/react-query` → native polling hook (Task 4).
- Existing `Badge.tsx` is wrong theme/non-clickable → new `Pill` primitive (Task 2).

**Out of scope (Phase 3):** admin config tab, dnd-kit reorder, visibility/enabled toggles, live preview card wiring, i18n strings, `show_bottom_upload` UI + `UploadProgressBar` gating.
