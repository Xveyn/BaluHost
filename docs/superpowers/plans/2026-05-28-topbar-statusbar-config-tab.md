# Topbar Status Strip — Phase 3: Admin Config Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give admins a UI under **System Control → System → Status Bar** to enable/disable pills, set per-pill visibility, drag-reorder them (dnd-kit), toggle the bottom upload bar, and preview the result live.

**Architecture:** A new `statusbar` tab in `SystemControlPage` renders `<StatusBarConfigTab>`, which loads the catalog+config via `usePillConfig`, renders a `@dnd-kit/sortable` list of `<PillRow>`s, and a live preview that reuses `<TopbarStatusStrip previewState={...}>` from Phase 2. Save issues `PUT /api/system/statusbar/config`.

**Tech Stack:** React 18, TypeScript, Tailwind, lucide-react, react-hot-toast (`toast`), react-i18next, **@dnd-kit/core + @dnd-kit/sortable + @dnd-kit/utilities (new dependencies)**, Vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-05-27-topbar-statusbar-design.md`

**Prerequisites:** Phase 1 (backend API) + Phase 2 (`<TopbarStatusStrip>`, `statusBar.ts` client) merged.

> **Decision (2026-05-28):** the user chose real drag-and-drop via dnd-kit over native up/down buttons, accepting the new dependency.

**Verified patterns:**
- Tabs: `SystemControlPage.tsx` — `CATEGORIES[].tabs` array of `{ id, labelKey, icon }`; `TabType` union (line 29); content via `{activeTab === 'x' && <Comp />}` (lines 186–210); `useTranslation('common')`; `systemControl.tabs.*` keys live in `common.json`.
- i18n: namespaces are registered in `client/src/i18n/index.ts` — import JSON, add to `resources.de`/`resources.en`, add to the `ns: [...]` array.
- Toast: `import toast from 'react-hot-toast'`; `toast.success(...)` / `toast.error(...)`.
- Config API client (Phase 2): `getStatusBarConfig()`, `updateStatusBarConfig(payload)` in `client/src/api/statusBar.ts`.

---

## File Structure

**Create:**
- `client/src/components/status-bar-config/usePillConfig.ts` — load/edit/save hook
- `client/src/components/status-bar-config/PillRow.tsx` — one sortable row
- `client/src/components/status-bar-config/StatusBarConfigTab.tsx` — the tab UI
- `client/src/components/status-bar-config/index.ts` — barrel export
- `client/src/i18n/locales/en/statusBar.json` + `client/src/i18n/locales/de/statusBar.json`
- Tests under `client/src/__tests__/components/status-bar-config/`

**Modify:**
- `client/package.json` — add dnd-kit deps (via npm install)
- `client/src/i18n/index.ts` — register `statusBar` namespace
- `client/src/i18n/locales/en/common.json` + `de/common.json` — add `systemControl.tabs.statusBar`
- `client/src/pages/SystemControlPage.tsx` — add `statusbar` tab + render
- The component that renders `<UploadProgressBar>` — gate by `show_bottom_upload`

---

## Task 1: Add dnd-kit dependencies

**Files:**
- Modify: `client/package.json` (+ lockfile)

- [ ] **Step 1: Install**

Run: `cd client && npm install @dnd-kit/core@^6 @dnd-kit/sortable@^8 @dnd-kit/utilities@^3`
Expected: three deps added to `dependencies` in `package.json`.

- [ ] **Step 2: Verify the build still works**

Run: `cd client && npm run build`
Expected: success (deps resolve, no version conflicts with React 18).

- [ ] **Step 3: Commit**

```bash
git add client/package.json client/package-lock.json
git commit -m "build(statusbar): add @dnd-kit for pill reordering"
```

---

## Task 2: i18n — statusBar namespace + tab label

**Files:**
- Create: `client/src/i18n/locales/en/statusBar.json`, `client/src/i18n/locales/de/statusBar.json`
- Modify: `client/src/i18n/index.ts`, `client/src/i18n/locales/en/common.json`, `client/src/i18n/locales/de/common.json`

- [ ] **Step 1: Create the EN namespace file**

Create `client/src/i18n/locales/en/statusBar.json`:

```json
{
  "tabTitle": "Topbar Status Strip",
  "description": "Choose which status pills appear in the topbar, who can see them, and their order.",
  "pills": {
    "power": { "name": "Power Profile" },
    "pihole": { "name": "Pi-hole DNS" },
    "uploads": { "name": "Uploads / Downloads" },
    "sync": { "name": "Sync" },
    "raid": { "name": "RAID Health" },
    "sleep": { "name": "Sleep Mode" },
    "vpn": { "name": "VPN Clients" },
    "temp": { "name": "Temperature / Fans" },
    "alwaysAwake": { "name": "Always Awake" },
    "scheduler": { "name": "Scheduler" },
    "backup": { "name": "Backup" }
  },
  "visibility": { "admin": "Admin only", "all": "All Users", "locked": "Admin only (locked)" },
  "enabled": "Enabled",
  "uploadBar": {
    "title": "Show bottom upload bar",
    "desc": "Independent from the Uploads pill in the topbar."
  },
  "preview": { "title": "Live Preview", "empty": "No pills enabled — the strip will be empty." },
  "save": "Save",
  "reset": "Reset to defaults",
  "saved": "Status bar settings saved",
  "saveFailed": "Failed to save status bar settings",
  "loadFailed": "Failed to load status bar settings"
}
```

- [ ] **Step 2: Create the DE namespace file**

Create `client/src/i18n/locales/de/statusBar.json`:

```json
{
  "tabTitle": "Topbar-Statusleiste",
  "description": "Lege fest, welche Status-Pills in der Topbar erscheinen, wer sie sieht und in welcher Reihenfolge.",
  "pills": {
    "power": { "name": "Energieprofil" },
    "pihole": { "name": "Pi-hole DNS" },
    "uploads": { "name": "Uploads / Downloads" },
    "sync": { "name": "Sync" },
    "raid": { "name": "RAID-Zustand" },
    "sleep": { "name": "Sleep-Modus" },
    "vpn": { "name": "VPN-Clients" },
    "temp": { "name": "Temperatur / Lüfter" },
    "alwaysAwake": { "name": "Immer wach" },
    "scheduler": { "name": "Scheduler" },
    "backup": { "name": "Backup" }
  },
  "visibility": { "admin": "Nur Admin", "all": "Alle Nutzer", "locked": "Nur Admin (gesperrt)" },
  "enabled": "Aktiv",
  "uploadBar": {
    "title": "Untere Upload-Leiste anzeigen",
    "desc": "Unabhängig vom Uploads-Pill in der Topbar."
  },
  "preview": { "title": "Live-Vorschau", "empty": "Keine Pills aktiv — die Leiste bleibt leer." },
  "save": "Speichern",
  "reset": "Auf Standard zurücksetzen",
  "saved": "Statusleisten-Einstellungen gespeichert",
  "saveFailed": "Speichern fehlgeschlagen",
  "loadFailed": "Laden fehlgeschlagen"
}
```

- [ ] **Step 3: Register the namespace**

In `client/src/i18n/index.ts`:

Add the imports (after the `pihole` imports near line 41):

```ts
import statusBarDe from './locales/de/statusBar.json';
import statusBarEn from './locales/en/statusBar.json';
```

Add to `resources.de` (after `pihole: piholeDe,`):

```ts
    statusBar: statusBarDe,
```

Add to `resources.en` (after `pihole: piholeEn,`):

```ts
    statusBar: statusBarEn,
```

Add `'statusBar'` to the `ns: [...]` array (line 93):

```ts
    ns: ['common', 'dashboard', 'fileManager', 'settings', 'admin', 'login', 'system', 'shares', 'plugins', 'devices', 'scheduler', 'notifications', 'updates', 'remoteServers', 'apiDocs', 'manual', 'setup', 'pihole', 'statusBar'],
```

- [ ] **Step 4: Add the tab label to common.json (both locales)**

In `client/src/i18n/locales/en/common.json`, find the `systemControl.tabs` object and add:

```json
"statusBar": "Status Bar"
```

In `client/src/i18n/locales/de/common.json`, same object:

```json
"statusBar": "Statusleiste"
```

> Locate the `systemControl` → `tabs` object first (it already contains `energy`, `fan`, `sleep`, etc.). Add the `statusBar` key alongside them. Keep valid JSON (commas).

- [ ] **Step 5: Validate JSON + build**

Run: `cd client && node -e "require('./src/i18n/locales/en/statusBar.json'); require('./src/i18n/locales/de/statusBar.json'); require('./src/i18n/locales/en/common.json'); require('./src/i18n/locales/de/common.json'); console.log('json ok')" && npm run build`
Expected: prints `json ok`, build succeeds.

- [ ] **Step 6: Commit**

```bash
git add client/src/i18n/
git commit -m "feat(statusbar): i18n statusBar namespace (de/en) + tab label"
```

---

## Task 3: `usePillConfig` hook

**Files:**
- Create: `client/src/components/status-bar-config/usePillConfig.ts`
- Test: `client/src/__tests__/components/status-bar-config/usePillConfig.test.ts`

The hook loads config, keeps an editable local copy, exposes mutators (toggle enabled, set visibility, reorder, set upload bar), and a `save()` that PUTs the local state.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/status-bar-config/usePillConfig.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

vi.mock('../../../api/statusBar', () => ({
  getStatusBarConfig: vi.fn(),
  updateStatusBarConfig: vi.fn(),
}));

import { getStatusBarConfig, updateStatusBarConfig } from '../../../api/statusBar';
import { usePillConfig } from '../../../components/status-bar-config/usePillConfig';

const sample = {
  pills: [
    { pill_id: 'power', name_key: 'statusBar.pills.power.name', enabled: false, visibility: 'admin', visibility_locked: false, sort_order: 0, href: '/x' },
    { pill_id: 'raid', name_key: 'statusBar.pills.raid.name', enabled: false, visibility: 'admin', visibility_locked: true, sort_order: 1, href: '/y' },
  ],
  show_bottom_upload: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  (getStatusBarConfig as any).mockResolvedValue(structuredClone(sample));
  (updateStatusBarConfig as any).mockResolvedValue(structuredClone(sample));
});

describe('usePillConfig', () => {
  it('loads config on mount', async () => {
    const { result } = renderHook(() => usePillConfig());
    await waitFor(() => expect(result.current.pills).toHaveLength(2));
    expect(result.current.showBottomUpload).toBe(true);
  });

  it('toggles enabled locally', async () => {
    const { result } = renderHook(() => usePillConfig());
    await waitFor(() => expect(result.current.pills).toHaveLength(2));
    act(() => result.current.setEnabled('power', true));
    expect(result.current.pills.find(p => p.pill_id === 'power')!.enabled).toBe(true);
  });

  it('save() PUTs current local state', async () => {
    const { result } = renderHook(() => usePillConfig());
    await waitFor(() => expect(result.current.pills).toHaveLength(2));
    act(() => result.current.setEnabled('power', true));
    await act(async () => { await result.current.save(); });
    expect(updateStatusBarConfig).toHaveBeenCalledTimes(1);
    const payload = (updateStatusBarConfig as any).mock.calls[0][0];
    expect(payload.pills.find((p: any) => p.pill_id === 'power').enabled).toBe(true);
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd client && npm run test -- usePillConfig.test`
Expected: FAIL — cannot import `usePillConfig`.

- [ ] **Step 3: Implement**

Create `client/src/components/status-bar-config/usePillConfig.ts`:

```ts
import { useCallback, useEffect, useState } from 'react';
import {
  getStatusBarConfig, updateStatusBarConfig,
  PillCatalogEntry, PillVisibility,
} from '../../api/statusBar';

export interface UsePillConfig {
  pills: PillCatalogEntry[];
  showBottomUpload: boolean;
  loading: boolean;
  saving: boolean;
  error: boolean;
  setEnabled: (id: string, enabled: boolean) => void;
  setVisibility: (id: string, visibility: PillVisibility) => void;
  setShowBottomUpload: (v: boolean) => void;
  reorder: (from: number, to: number) => void;
  save: () => Promise<void>;
  reload: () => Promise<void>;
}

function reindex(pills: PillCatalogEntry[]): PillCatalogEntry[] {
  return pills.map((p, i) => ({ ...p, sort_order: i }));
}

export function usePillConfig(): UsePillConfig {
  const [pills, setPills] = useState<PillCatalogEntry[]>([]);
  const [showBottomUpload, setShow] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const cfg = await getStatusBarConfig();
      setPills([...cfg.pills].sort((a, b) => a.sort_order - b.sort_order));
      setShow(cfg.show_bottom_upload);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const setEnabled = useCallback((id: string, enabled: boolean) => {
    setPills(prev => prev.map(p => (p.pill_id === id ? { ...p, enabled } : p)));
  }, []);

  const setVisibility = useCallback((id: string, visibility: PillVisibility) => {
    setPills(prev => prev.map(p => (p.pill_id === id ? { ...p, visibility } : p)));
  }, []);

  const reorder = useCallback((from: number, to: number) => {
    setPills(prev => {
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return reindex(next);
    });
  }, []);

  const save = useCallback(async () => {
    setSaving(true);
    try {
      await updateStatusBarConfig({
        pills: pills.map(p => ({
          pill_id: p.pill_id, enabled: p.enabled,
          visibility: p.visibility, sort_order: p.sort_order,
        })),
        show_bottom_upload: showBottomUpload,
      });
    } finally {
      setSaving(false);
    }
  }, [pills, showBottomUpload]);

  return {
    pills, showBottomUpload, loading, saving, error,
    setEnabled, setVisibility, setShowBottomUpload: setShow, reorder, save, reload,
  };
}
```

- [ ] **Step 4: Run — should pass**

Run: `cd client && npm run test -- usePillConfig.test`
Expected: PASS (3)

- [ ] **Step 5: Commit**

```bash
git add client/src/components/status-bar-config/usePillConfig.ts client/src/__tests__/components/status-bar-config/usePillConfig.test.ts
git commit -m "feat(statusbar): usePillConfig admin config hook"
```

---

## Task 4: `<PillRow>` sortable row

**Files:**
- Create: `client/src/components/status-bar-config/PillRow.tsx`
- Test: `client/src/__tests__/components/status-bar-config/PillRow.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/status-bar-config/PillRow.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DndContext } from '@dnd-kit/core';
import { SortableContext } from '@dnd-kit/sortable';
import { PillRow } from '../../../components/status-bar-config/PillRow';
import type { PillCatalogEntry } from '../../../api/statusBar';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

function wrap(entry: PillCatalogEntry, handlers = {}) {
  const props = { entry, onToggleEnabled: vi.fn(), onSetVisibility: vi.fn(), ...handlers };
  return render(
    <DndContext>
      <SortableContext items={[entry.pill_id]}>
        <PillRow {...props} />
      </SortableContext>
    </DndContext>,
  );
}

const base: PillCatalogEntry = {
  pill_id: 'power', name_key: 'statusBar.pills.power.name', enabled: false,
  visibility: 'admin', visibility_locked: false, sort_order: 0, href: '/x',
};

describe('PillRow', () => {
  it('renders the pill name', () => {
    wrap(base);
    expect(screen.getByText('statusBar.pills.power.name')).toBeInTheDocument();
  });

  it('calls onToggleEnabled when the enabled switch is clicked', () => {
    const onToggleEnabled = vi.fn();
    wrap(base, { onToggleEnabled });
    fireEvent.click(screen.getByRole('switch'));
    expect(onToggleEnabled).toHaveBeenCalledWith('power', true);
  });

  it('disables the visibility select for a locked pill', () => {
    wrap({ ...base, pill_id: 'raid', visibility_locked: true });
    expect(screen.getByRole('combobox')).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd client && npm run test -- PillRow.test`
Expected: FAIL — cannot import `PillRow`.

- [ ] **Step 3: Implement**

Create `client/src/components/status-bar-config/PillRow.tsx`:

```tsx
import React from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { PillCatalogEntry, PillVisibility } from '../../api/statusBar';

interface Props {
  entry: PillCatalogEntry;
  onToggleEnabled: (id: string, enabled: boolean) => void;
  onSetVisibility: (id: string, visibility: PillVisibility) => void;
}

export function PillRow({ entry, onToggleEnabled, onSetVisibility }: Props) {
  const { t } = useTranslation('statusBar');
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: entry.pill_id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2"
    >
      <button
        type="button"
        className="cursor-grab text-slate-500 hover:text-slate-300 touch-none"
        aria-label="drag handle"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="h-4 w-4" />
      </button>

      <span className="flex-1 text-sm text-slate-200">{t(entry.name_key)}</span>

      {entry.visibility_locked ? (
        <span className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-400">
          <Lock className="h-3 w-3" />
          {t('visibility.locked')}
        </span>
      ) : null}

      <select
        className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 disabled:opacity-50"
        value={entry.visibility}
        disabled={entry.visibility_locked}
        onChange={(e) => onSetVisibility(entry.pill_id, e.target.value as PillVisibility)}
      >
        <option value="admin">{t('visibility.admin')}</option>
        <option value="all">{t('visibility.all')}</option>
      </select>

      <button
        type="button"
        role="switch"
        aria-checked={entry.enabled}
        aria-label={t('enabled')}
        onClick={() => onToggleEnabled(entry.pill_id, !entry.enabled)}
        className={`relative h-5 w-9 rounded-full transition ${entry.enabled ? 'bg-emerald-500/70' : 'bg-slate-700'}`}
      >
        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${entry.enabled ? 'left-4' : 'left-0.5'}`} />
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run — should pass**

Run: `cd client && npm run test -- PillRow.test`
Expected: PASS (3)

- [ ] **Step 5: Commit**

```bash
git add client/src/components/status-bar-config/PillRow.tsx client/src/__tests__/components/status-bar-config/PillRow.test.tsx
git commit -m "feat(statusbar): sortable PillRow with locked-visibility handling"
```

---

## Task 5: `<StatusBarConfigTab>`

**Files:**
- Create: `client/src/components/status-bar-config/StatusBarConfigTab.tsx`
- Create: `client/src/components/status-bar-config/index.ts`
- Test: `client/src/__tests__/components/status-bar-config/StatusBarConfigTab.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/status-bar-config/StatusBarConfigTab.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../../api/statusBar', () => ({
  getStatusBarConfig: vi.fn(),
  updateStatusBarConfig: vi.fn(),
  getStatusBarState: vi.fn().mockResolvedValue({ pills: [], show_bottom_upload: true }),
}));

import { getStatusBarConfig, updateStatusBarConfig } from '../../../api/statusBar';
import { StatusBarConfigTab } from '../../../components/status-bar-config/StatusBarConfigTab';

const cfg = {
  pills: [
    { pill_id: 'power', name_key: 'statusBar.pills.power.name', enabled: false, visibility: 'admin', visibility_locked: false, sort_order: 0, href: '/x' },
    { pill_id: 'raid', name_key: 'statusBar.pills.raid.name', enabled: false, visibility: 'admin', visibility_locked: true, sort_order: 1, href: '/y' },
  ],
  show_bottom_upload: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  (getStatusBarConfig as any).mockResolvedValue(structuredClone(cfg));
  (updateStatusBarConfig as any).mockResolvedValue(structuredClone(cfg));
});

function renderTab() {
  return render(<MemoryRouter><StatusBarConfigTab /></MemoryRouter>);
}

describe('StatusBarConfigTab', () => {
  it('lists all pills after load', async () => {
    renderTab();
    await waitFor(() => expect(screen.getByText('statusBar.pills.power.name')).toBeInTheDocument());
    expect(screen.getByText('statusBar.pills.raid.name')).toBeInTheDocument();
  });

  it('save button calls updateStatusBarConfig', async () => {
    renderTab();
    await waitFor(() => expect(screen.getByText('statusBar.save')).toBeInTheDocument());
    await act(async () => { fireEvent.click(screen.getByText('statusBar.save')); });
    expect(updateStatusBarConfig).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd client && npm run test -- StatusBarConfigTab.test`
Expected: FAIL — cannot import `StatusBarConfigTab`.

- [ ] **Step 3: Implement**

Create `client/src/components/status-bar-config/StatusBarConfigTab.tsx`:

```tsx
import React, { useMemo } from 'react';
import {
  DndContext, closestCenter, KeyboardSensor, PointerSensor,
  useSensor, useSensors, DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import { usePillConfig } from './usePillConfig';
import { PillRow } from './PillRow';
import { TopbarStatusStrip } from '../topbar/TopbarStatusStrip';
import type { StatusBarStateResponse } from '../../api/statusBar';

export function StatusBarConfigTab() {
  const { t } = useTranslation('statusBar');
  const cfg = usePillConfig();
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = cfg.pills.findIndex(p => p.pill_id === active.id);
    const to = cfg.pills.findIndex(p => p.pill_id === over.id);
    if (from >= 0 && to >= 0) cfg.reorder(from, to);
  };

  const onSave = async () => {
    try {
      await cfg.save();
      toast.success(t('saved'));
    } catch {
      toast.error(t('saveFailed'));
    }
  };

  // Build a preview payload from the current (unsaved) enabled pills.
  const previewState: StatusBarStateResponse = useMemo(() => ({
    pills: cfg.pills
      .filter(p => p.enabled)
      .map(p => ({
        id: p.pill_id, kind: 'state' as const, tone: 'neutral' as const,
        label: t(p.name_key), href: p.href, value: null, icon: null, extra: null,
      })),
    show_bottom_upload: cfg.showBottomUpload,
  }), [cfg.pills, cfg.showBottomUpload, t]);

  if (cfg.loading) {
    return <div className="py-8 text-center text-slate-400">…</div>;
  }
  if (cfg.error) {
    return <div className="py-8 text-center text-rose-400">{t('loadFailed')}</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">{t('tabTitle')}</h2>
        <p className="mt-1 text-sm text-slate-400">{t('description')}</p>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={cfg.pills.map(p => p.pill_id)} strategy={verticalListSortingStrategy}>
          <div className="space-y-2">
            {cfg.pills.map(entry => (
              <PillRow
                key={entry.pill_id}
                entry={entry}
                onToggleEnabled={cfg.setEnabled}
                onSetVisibility={cfg.setVisibility}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3">
        <div>
          <p className="text-sm text-slate-200">{t('uploadBar.title')}</p>
          <p className="text-xs text-slate-500">{t('uploadBar.desc')}</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={cfg.showBottomUpload}
          onClick={() => cfg.setShowBottomUpload(!cfg.showBottomUpload)}
          className={`relative h-5 w-9 rounded-full transition ${cfg.showBottomUpload ? 'bg-emerald-500/70' : 'bg-slate-700'}`}
        >
          <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${cfg.showBottomUpload ? 'left-4' : 'left-0.5'}`} />
        </button>
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3">
        <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{t('preview.title')}</p>
        {previewState.pills.length === 0
          ? <p className="text-sm text-slate-500">{t('preview.empty')}</p>
          : <TopbarStatusStrip previewState={previewState} />}
      </div>

      <div className="flex items-center gap-3">
        <button type="button" onClick={onSave} disabled={cfg.saving} className="btn btn-primary">
          {t('save')}
        </button>
        <button type="button" onClick={cfg.reload} disabled={cfg.saving} className="btn btn-secondary">
          {t('reset')}
        </button>
      </div>
    </div>
  );
}
```

Create `client/src/components/status-bar-config/index.ts`:

```ts
export { StatusBarConfigTab } from './StatusBarConfigTab';
```

- [ ] **Step 4: Run — should pass**

Run: `cd client && npm run test -- StatusBarConfigTab.test`
Expected: PASS (2)

- [ ] **Step 5: Commit**

```bash
git add client/src/components/status-bar-config/ client/src/__tests__/components/status-bar-config/StatusBarConfigTab.test.tsx
git commit -m "feat(statusbar): admin config tab with dnd reorder + live preview"
```

---

## Task 6: Register the tab in SystemControlPage

**Files:**
- Modify: `client/src/pages/SystemControlPage.tsx`

- [ ] **Step 1: Add the import + icon**

In `client/src/pages/SystemControlPage.tsx`, add `LayoutPanelTop` to the lucide import (line 11):

```tsx
import { Zap, Fan, HardDrive, Archive, Shield, Server, History, Plug, Gauge, FolderOpen, Share2, Cpu, Globe, Settings, Moon, Variable, Bell, CircuitBoard, LayoutPanelTop } from 'lucide-react';
```

And add the component import (after the `BaluPiSetup` import near line 27):

```tsx
import { StatusBarConfigTab } from '../components/status-bar-config';
```

- [ ] **Step 2: Extend the TabType union**

Change the `TabType` (line 29) to include `'statusbar'`:

```tsx
type TabType = 'energy' | 'fan' | 'sleep' | 'raid' | 'backup' | 'ssdcache' | 'vpn' | 'webdav' | 'samba' | 'firebase' | 'services' | 'vcl' | 'smart' | 'ratelimits' | 'envconfig' | 'balupi' | 'statusbar';
```

- [ ] **Step 3: Add the tab to the `system` category**

In the `system` category's `tabs` array (after the `balupi` entry, line 87), add:

```tsx
      { id: 'statusbar', labelKey: 'systemControl.tabs.statusBar', icon: <LayoutPanelTop className="h-5 w-5" /> },
```

- [ ] **Step 4: Add the content render line**

In the Tab Content block (after the `balupi` line, line 210), add:

```tsx
        {activeTab === 'statusbar' && <StatusBarConfigTab />}
```

- [ ] **Step 5: Build + manual check**

Run: `cd client && npm run build`
Expected: success (TabType union now includes statusbar, no type errors).

Then run `python start_dev.py`, log in as admin, go to **System Control → System → Status Bar**. Verify: 11 rows listed, drag to reorder works, toggles flip, locked pills show the lock badge and a disabled visibility select, Save persists (reload page → order/toggles retained), the Live Preview updates as you toggle.

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/SystemControlPage.tsx
git commit -m "feat(statusbar): register Status Bar tab under System Control"
```

---

## Task 7: Gate the bottom upload bar by `show_bottom_upload`

**Files:**
- Modify: the component that renders `<UploadProgressBar>` (locate it — see Step 1)

- [ ] **Step 1: Locate the render site**

`<UploadProgressBar>` is a top-level component (per `client/src/components/CLAUDE.md` it's "Global file upload progress"). Find where it is mounted — search the codebase for `UploadProgressBar` usage (it is rendered in a layout/app-level file, likely `client/src/components/Layout.tsx` or `client/src/App.tsx`). Use `mcp__vectordb-search__search_code` with query "UploadProgressBar component render" and `projectPath` `D:/Programme (x86)/Baluhost`, or open `Layout.tsx`/`App.tsx`.

- [ ] **Step 2: Add a lightweight setting fetch**

In the file that renders `<UploadProgressBar>`, fetch `show_bottom_upload` once on mount and gate the render. Add near the other hooks in that component:

```tsx
import { useEffect, useState } from 'react';
import { getStatusBarState } from '../api/statusBar'; // adjust relative path to lib location

const [showUploadBar, setShowUploadBar] = useState(true);
useEffect(() => {
  let cancelled = false;
  getStatusBarState()
    .then((s) => { if (!cancelled) setShowUploadBar(s.show_bottom_upload); })
    .catch(() => { /* default to showing on error */ });
  return () => { cancelled = true; };
}, []);
```

Then gate the existing render:

```tsx
{showUploadBar && <UploadProgressBar />}
```

> The `/state` payload already carries `show_bottom_upload`, so no new endpoint is needed. The setting changes rarely; fetching once on mount is sufficient. If the render site is inside `<TopbarStatusStrip>`'s parent that already has state, reuse that instead of a second fetch — but a one-shot fetch here is acceptable and isolated.

- [ ] **Step 3: Build + manual check**

Run: `cd client && npm run build`
Then in the running dev app: toggle "Show bottom upload bar" off in the config tab, Save, reload → start an upload → confirm the bottom `<UploadProgressBar>` does NOT appear. Toggle on → it appears again.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(statusbar): gate bottom upload bar by show_bottom_upload setting"
```

---

## Task 8: Phase 3 verification + full smoketest

**Files:** none (verification only)

- [ ] **Step 1: Run all status-bar config tests**

Run: `cd client && npm run test -- usePillConfig PillRow StatusBarConfigTab`
Expected: ALL PASS.

- [ ] **Step 2: Full build + lint**

Run: `cd client && npm run build && npm run lint`
Expected: success; no new lint errors in created files.

- [ ] **Step 3: End-to-end manual smoketest (from the spec)**

With `python start_dev.py` running:
1. Login as admin → System Control → System → Status Bar.
2. Enable Power, Pi-hole, Uploads, Always Awake, Scheduler, Backup with mixed visibilities. Save.
3. Drag-reorder → Save → verify topbar reflects the new order.
4. Toggle bottom-upload off → Save → trigger an upload → `<UploadProgressBar>` absent.
5. Login as a non-admin user (second browser) → only "All Users" pills visible; Always-Awake / Scheduler / Backup NOT visible.
6. Toggle Always Awake on with a 5-minute preset (Sleep page) → topbar pill shows a live countdown ticking down each second.
7. Trigger a manual scheduler run → Scheduler pill appears with count, job name in tooltip.
8. Resize below `lg` → strip disappears. Open a Pi-mode build → strip not present.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "test(statusbar): config tab phase 3 green + smoketest pass"
```

---

## Self-Review (completed during planning)

**Spec coverage:**
- Admin enable/disable per pill → Tasks 3–5 ✓
- Per-pill visibility select, locked pills read-only → Task 4 ✓
- Drag-to-reorder (dnd-kit) → Tasks 1, 4, 5 ✓
- `show_bottom_upload` toggle independent of Uploads pill → Tasks 5, 7 ✓
- Live preview via `<TopbarStatusStrip previewState>` → Task 5 ✓ (reuses Phase 2 prop)
- Tab under System Control → System → Task 6 ✓
- i18n DE+EN, new `statusBar` namespace + `systemControl.tabs.statusBar` → Task 2 ✓
- Save / Reset → Task 5 ✓

**Decision folded in:** dnd-kit added as a new dependency (user choice over native up/down buttons).

**Cross-phase consistency check:**
- `usePillConfig` payload shape (`pill_id`/`enabled`/`visibility`/`sort_order` + `show_bottom_upload`) matches Phase 1 `StatusBarConfigUpdate` and the Phase 2 `StatusBarConfigUpdate` TS type ✓
- `TopbarStatusStrip` `previewState` prop defined in Phase 2 Task 8, consumed here in Task 5 ✓
- `PillCatalogEntry` type (Phase 2 `statusBar.ts`) used by `usePillConfig`/`PillRow` ✓
- Locked-visibility: UI disables the select (Task 4) AND backend rejects `all` (Phase 1) — defense in depth ✓

**Note for implementer:** the preview pills render with `tone: 'neutral'` and no live values (it's a layout preview of *which* pills + order, not their live data). The real strip computes tones/values server-side. This matches the spec's "render the supplied state" intent for an unsaved-config preview without an API roundtrip.
```
