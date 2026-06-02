# PowerMenu „Desktop deaktivieren" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine Ein-Weg-Schnellaktion „Desktop deaktivieren" im PowerMenu (Power-Button oben rechts), die nur erscheint, wenn die KDE-Bildschirme laufen, und per Klick sofort `disableDesktop()` (DPMS-Screen-Off) auslöst.

**Architecture:** Reine Frontend-Änderung an einer Komponente (`client/src/components/PowerMenu.tsx`) plus i18n-Keys. Status wird beim Öffnen des Menüs über das bestehende `getDesktopStatus()` geladen; der Punkt rendert conditional auf `state === 'running'`. Kein Backend-/API-Client-/Schema-Change — `getDesktopStatus`/`disableDesktop` existieren bereits in `client/src/api/desktop.ts`.

**Tech Stack:** React + TypeScript, Tailwind, react-i18next, react-hot-toast, lucide-react; Vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-06-02-powermenu-desktop-disable-design.md`

---

## Prerequisites

This worktree has no `node_modules`. Before running any `npm` command (vitest/build) once:

```bash
cd client && npm install
```

(May take a few minutes. Required for Task 1 Step 2 onward and Task 3.)

## File Structure

| Datei | Verantwortung | Aktion |
|---|---|---|
| `client/src/components/PowerMenu.tsx` | PowerMenu-Dropdown — neue Aktion + Status-Laden + Handler | Modify |
| `client/src/i18n/locales/en/common.json` | EN-Strings (`powerMenu.*`) | Modify |
| `client/src/i18n/locales/de/common.json` | DE-Strings (`powerMenu.*`) | Modify |
| `client/src/__tests__/components/PowerMenu.test.tsx` | Vitest-Test der neuen Aktion | Create |

Reference — the current `PowerMenu.tsx` relevant regions (origin/main):
- Imports (line 3): `import { Power, PowerOff, RotateCcw, LogOut, Moon, Pause } from 'lucide-react';`
- Sleep API import (line 5): `import { getSleepStatus, enterSoftSleep, enterSuspend } from '../api/sleep';`
- State (line 19): `const [sleepAvailable, setSleepAvailable] = useState(false);`
- Availability `useEffect` (lines 23-29): calls `getSleepStatus()` on open.
- The Standby button closes at line 144; the `{sleepAvailable && (…)}` block closes at line 146; the wrapping `<div className="p-1.5">` closes at line 147.

---

## Task 1: PowerMenu component + Vitest test

Add the quick action (imports, status state, fetch, handler, conditional menu item) to `PowerMenu.tsx`, test-first.

**Files:**
- Create: `client/src/__tests__/components/PowerMenu.test.tsx`
- Modify: `client/src/components/PowerMenu.tsx`

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/PowerMenu.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

// Deterministic translations: return the inline default (2nd arg), else the key.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_key: string, def?: string) => def ?? _key }),
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../api/sleep', () => ({
  getSleepStatus: vi.fn(),
  enterSoftSleep: vi.fn(),
  enterSuspend: vi.fn(),
}));

vi.mock('../../api/desktop', () => ({
  getDesktopStatus: vi.fn(),
  disableDesktop: vi.fn(),
}));

import PowerMenu from '../../components/PowerMenu';
import { getSleepStatus } from '../../api/sleep';
import { getDesktopStatus, disableDesktop } from '../../api/desktop';
import toast from 'react-hot-toast';

const baseProps = {
  isAdmin: true,
  onShutdown: vi.fn().mockResolvedValue(undefined),
  onRestart: vi.fn().mockResolvedValue(undefined),
  onLogout: vi.fn(),
};

function openMenu() {
  fireEvent.click(screen.getByTitle('Power'));
}

describe('PowerMenu — disable desktop quick action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getSleepStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({});
  });

  it('shows "Disable desktop" when displays are running', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'running', display_manager: 'sddm', detail: null,
    });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    expect(await screen.findByText('Disable desktop')).toBeInTheDocument();
  });

  it('hides "Disable desktop" when displays are stopped', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'stopped', display_manager: 'sddm', detail: null,
    });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    await waitFor(() => expect(getDesktopStatus).toHaveBeenCalled());
    await act(async () => {});
    expect(screen.queryByText('Disable desktop')).not.toBeInTheDocument();
  });

  it('hides "Disable desktop" when the status lookup fails', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('no desktop'));
    render(<PowerMenu {...baseProps} />);
    openMenu();
    await waitFor(() => expect(getDesktopStatus).toHaveBeenCalled());
    await act(async () => {});
    expect(screen.queryByText('Disable desktop')).not.toBeInTheDocument();
  });

  it('clicking it calls disableDesktop and shows a success toast', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'running', display_manager: 'sddm', detail: null,
    });
    (disableDesktop as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, message: 'ok' });
    render(<PowerMenu {...baseProps} />);
    openMenu();
    const item = await screen.findByText('Disable desktop');
    fireEvent.click(item);
    await waitFor(() => expect(disableDesktop).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it('does not show "Disable desktop" for non-admins', async () => {
    (getDesktopStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: 'running', display_manager: 'sddm', detail: null,
    });
    render(<PowerMenu {...baseProps} isAdmin={false} />);
    openMenu();
    await act(async () => {});
    expect(screen.queryByText('Disable desktop')).not.toBeInTheDocument();
    expect(getDesktopStatus).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test — expect FAIL**

Run: `cd client && npm test -- PowerMenu`
Expected: FAIL — the "Disable desktop" item does not exist yet (`findByText` times out; `disableDesktop` never called).

- [ ] **Step 3: Add imports**

In `client/src/components/PowerMenu.tsx`, change the lucide import (line 3) to include `MonitorOff`:

```tsx
import { Power, PowerOff, RotateCcw, LogOut, Moon, Pause, MonitorOff } from 'lucide-react';
```

Directly after the sleep API import (line 5), add the desktop API import:

```tsx
import { getDesktopStatus, disableDesktop, type DesktopState } from '../api/desktop';
```

- [ ] **Step 4: Add status state**

Immediately after the `sleepAvailable` state (line 19), add:

```tsx
  const [desktopState, setDesktopState] = useState<DesktopState | null>(null);
```

- [ ] **Step 5: Fetch desktop status when the menu opens**

Replace the availability `useEffect` (lines 23-29) with:

```tsx
  // Check sleep + desktop availability when dropdown opens
  useEffect(() => {
    if (isOpen && isAdmin) {
      getSleepStatus()
        .then(() => setSleepAvailable(true))
        .catch(() => setSleepAvailable(false));
      getDesktopStatus()
        .then((s) => setDesktopState(s.state))
        .catch(() => setDesktopState(null));
    }
  }, [isOpen, isAdmin]);
```

- [ ] **Step 6: Add the click handler**

Immediately after the `handleConfirm` function (after its closing `};`, around line 71), add:

```tsx
  const handleDisableDesktop = async () => {
    setIsOpen(false);
    try {
      const result = await disableDesktop();
      if (result.success) {
        toast.success(t('powerMenu.desktopDisabled', 'Desktop disabled'));
      } else {
        toast.error(result.message || t('powerMenu.desktopDisableFailed', 'Failed to disable desktop'));
      }
    } catch {
      toast.error(t('powerMenu.desktopDisableFailed', 'Failed to disable desktop'));
    }
  };
```

- [ ] **Step 7: Add the menu item**

In `PowerMenu.tsx`, insert the new button between the close of the `{sleepAvailable && (…)}` block (`)}` on line 146) and the close of the `<div className="p-1.5">` (`</div>` on line 147) — i.e. as the last child of that admin-actions `<div>`:

```tsx
                  {desktopState === 'running' && (
                    <button
                      onClick={handleDisableDesktop}
                      className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-cyan-500/10"
                    >
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-cyan-500/30 bg-cyan-500/10">
                        <MonitorOff className="h-4 w-4 text-cyan-400" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-slate-100">{t('powerMenu.desktopDisable', 'Disable desktop')}</p>
                        <p className="text-xs text-slate-400">{t('powerMenu.desktopDisableDesc', 'Turn off displays (saves GPU power)')}</p>
                      </div>
                    </button>
                  )}
```

- [ ] **Step 8: Run the test — expect PASS**

Run: `cd client && npm test -- PowerMenu`
Expected: all 5 tests PASS.

- [ ] **Step 9: Commit**

```bash
git add client/src/components/PowerMenu.tsx client/src/__tests__/components/PowerMenu.test.tsx
git commit -m "feat(power): add 'disable desktop' quick action to PowerMenu"
```

---

## Task 2: i18n strings (DE + EN)

Add the four `powerMenu.*` keys so production shows localized text (the component already falls back to inline English defaults).

**Files:**
- Modify: `client/src/i18n/locales/en/common.json`
- Modify: `client/src/i18n/locales/de/common.json`

- [ ] **Step 1: English keys**

In `client/src/i18n/locales/en/common.json`, in the `powerMenu` object, replace the line:

```json
    "suspendFailed": "Failed to suspend system"
```

with:

```json
    "suspendFailed": "Failed to suspend system",
    "desktopDisable": "Disable desktop",
    "desktopDisableDesc": "Turn off displays (saves GPU power)",
    "desktopDisabled": "Desktop disabled",
    "desktopDisableFailed": "Failed to disable desktop"
```

- [ ] **Step 2: German keys**

In `client/src/i18n/locales/de/common.json`, in the `powerMenu` object, replace the line:

```json
    "suspendFailed": "Standby konnte nicht aktiviert werden"
```

with:

```json
    "suspendFailed": "Standby konnte nicht aktiviert werden",
    "desktopDisable": "Desktop deaktivieren",
    "desktopDisableDesc": "Bildschirme ausschalten (GPU spart Strom)",
    "desktopDisabled": "Desktop deaktiviert",
    "desktopDisableFailed": "Desktop konnte nicht deaktiviert werden"
```

- [ ] **Step 3: Validate both JSON files parse**

Run: `cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en/common.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/de/common.json','utf8')); console.log('JSON OK')"`
Expected: `JSON OK` (no trailing-comma / syntax error).

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/en/common.json client/src/i18n/locales/de/common.json
git commit -m "feat(power): i18n strings for PowerMenu disable-desktop action (de+en)"
```

---

## Task 3: Verification

**Files:** none changed.

- [ ] **Step 1: Type-check + full PowerMenu test**

Run: `cd client && npx tsc --noEmit && npm test -- PowerMenu`
Expected: tsc passes (no type errors); 5 PowerMenu tests PASS.

- [ ] **Step 2: Production build**

Run: `cd client && npm run build`
Expected: build succeeds, no unresolved-import / missing-icon warnings for `MonitorOff`.

- [ ] **Step 3: Manual smoke (optional, on the KDE box / dev)**

In dev (`python start_dev.py`, dev backend reports `state='running'`): open the PowerMenu (top-right power button) as admin → a cyan **„Desktop deaktivieren"** item appears below **Standby**. Click → toast „Desktop deaktiviert", menu closes. (Dev backend just flips in-memory state; reopen → item gone since state is now `stopped`.)

---

## Out of Scope (per spec)

- Toggle / re-enable in the PowerMenu (stays on the Sleep page)
- Confirmation dialog (action is reversible → immediate)
- Backend `available` flag / panel gating fix
- Mobile / Pi rendering
