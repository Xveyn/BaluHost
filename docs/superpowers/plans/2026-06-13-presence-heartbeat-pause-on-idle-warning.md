# Presence Heartbeat: Pause on Idle-Logout Warning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pause the presence heartbeat while the idle-auto-logout warning dialog is visible, so a forgotten background tab in `session` mode no longer blocks True Suspend for up to ~1 h (GitHub issue #222).

**Architecture:** Option A — lift the `usePresenceHeartbeat()` call out of `Layout` up into `AppRoutes` (`App.tsx`), where `useIdleTimeout`'s `warningVisible` state already lives. Pass `paused: warningVisible` and `enabled: user !== null` into the hook. The frequently-toggling `paused` flag is read through a ref so the long-lived `setInterval` is never torn down on toggle; `enabled` (rare, login/logout only) gates the whole effect.

**Tech Stack:** React 18 + TypeScript, Vitest + @testing-library/react (`renderHook`), Vite. All changes are client-side only — no backend touch.

---

## Background / Current State (on `origin/main`)

- `client/src/hooks/usePresenceHeartbeat.ts` — exports `usePresenceHeartbeat(): void`, no arguments. Single `useEffect(…, [])`; `beat()` already has the guard `if (mode === 'active' && document.visibilityState !== 'visible') return;`. `mode`/`intervalMs`/`timer` are mutable closure locals; `schedule()` (re)creates the `setInterval`.
- `client/src/hooks/useIdleTimeout.ts` — returns `{ warningVisible, secondsRemaining, resetTimer }`. `warningVisible` flips `true` when the 60 s logout countdown starts, `false` on `resetTimer()`.
- `client/src/App.tsx`
  - line 11: `import { useIdleTimeout } from './hooks/useIdleTimeout';`
  - line 145: `function AppRoutes()`
  - line 146: `const { user, logout, loading, isAdmin } = useAuth();`
  - lines 148–151: `const { warningVisible, secondsRemaining, resetTimer } = useIdleTimeout({ onLogout: logout, enabled: user !== null });`
  - line 154: `if (loading) return <LoadingScreen … />;` (early return — all hooks must be called before this line)
- `client/src/components/Layout.tsx`
  - line 22: `import { usePresenceHeartbeat } from '../hooks/usePresenceHeartbeat';`
  - line 123: `usePresenceHeartbeat();` (inside `export default function Layout`)
- Existing test: `client/src/__tests__/hooks/usePresenceHeartbeat.test.ts` — 8 tests, all call `usePresenceHeartbeat()` with no args (stays valid because the new option object defaults).
- API type (`client/src/api/sleep.ts:56`): `export type PresenceMode = 'active' | 'session';`

**Out of scope (deferred):** Issue point 3 ("send an immediate beat on *Stay logged in*"). Rationale: when `paused` flips back to `false`, the `setInterval` is still running (it is never cleared, because `paused` lives in a ref), so the next tick (≤45 s) resumes beats. With a 3-min presence timeout, a one-interval gap is harmless. Implementing an immediate beat would require exposing `beat()` outside the effect closure — extra surface not justified for a Low-severity fix. Document this as a deliberate skip.

---

## File Structure

- **Modify** `client/src/hooks/usePresenceHeartbeat.ts` — add `UsePresenceHeartbeatOptions { paused?, enabled? }`; `paused` via ref guard in `beat()`; `enabled` gates the effect.
- **Modify** `client/src/__tests__/hooks/usePresenceHeartbeat.test.ts` — add tests for `paused` (skip + resume) and `enabled: false` (no beats). Existing tests remain unchanged.
- **Modify** `client/src/App.tsx` — import the hook; call `usePresenceHeartbeat({ paused: warningVisible, enabled: user !== null })` in `AppRoutes`, right after `useIdleTimeout`, before the `if (loading)` early return.
- **Modify** `client/src/components/Layout.tsx` — remove the import (line 22) and the call (line 123).
- **Modify** `client/src/hooks/CLAUDE.md` — the `usePresenceHeartbeat.ts` row says "mounted once in Layout"; update it to reflect the new mount location (AppRoutes, auth-gated) and the idle-pause behavior.

---

## Task 1: Extend `usePresenceHeartbeat` with `paused` + `enabled` options

**Files:**
- Modify: `client/src/hooks/usePresenceHeartbeat.ts`
- Test: `client/src/__tests__/hooks/usePresenceHeartbeat.test.ts`

- [ ] **Step 1: Write the failing tests**

Append these three tests inside the existing `describe('usePresenceHeartbeat', …)` block in `client/src/__tests__/hooks/usePresenceHeartbeat.test.ts` (after the last existing test, before the closing `});` of the `describe`):

```typescript
  it('skips heartbeats while paused (session mode, visible)', async () => {
    mockedSend.mockResolvedValue({
      present: true,
      enabled: true,
      mode: 'session',
      heartbeat_interval_seconds: 45,
      timeout_minutes: 3,
    });
    const { rerender } = renderHook(
      ({ paused }) => usePresenceHeartbeat({ paused }),
      { initialProps: { paused: false } },
    );
    await flushAsync(); // initial beat -> learns mode 'session'
    expect(mockedSend).toHaveBeenCalledTimes(1);

    rerender({ paused: true });
    await act(async () => { vi.advanceTimersByTime(3 * 45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(1); // no new beats while paused
  });

  it('resumes heartbeats after un-pausing', async () => {
    const { rerender } = renderHook(
      ({ paused }) => usePresenceHeartbeat({ paused }),
      { initialProps: { paused: true } },
    );
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(0); // paused from mount: even initial beat skipped

    rerender({ paused: false });
    await act(async () => { vi.advanceTimersByTime(45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(1);
  });

  it('sends nothing when disabled', async () => {
    renderHook(() => usePresenceHeartbeat({ enabled: false }));
    await flushAsync();
    await act(async () => { vi.advanceTimersByTime(3 * 45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(0);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd client && npx vitest run src/__tests__/hooks/usePresenceHeartbeat.test.ts`
Expected: the three new tests FAIL. Most likely the "paused" tests fail because beats are still sent (no `paused` handling yet), and TypeScript/runtime accepts the option object but ignores it. (`usePresenceHeartbeat({ paused })` is currently a type error since the hook takes no args — the test file will fail to compile, which counts as failing.)

- [ ] **Step 3: Implement the option handling in the hook**

Replace the full contents of `client/src/hooks/usePresenceHeartbeat.ts` with:

```typescript
/**
 * Presence heartbeat (issue #214, idle-pause #222).
 *
 * Sends POST /api/system/sleep/presence on an interval so the backend knows
 * a user is actively present and will not auto-escalate to true suspend.
 *
 * Mode is learned from the heartbeat response:
 * - 'active'  (default): beats only while the tab is visible — a forgotten
 *   background tab does not keep the server awake.
 * - 'session': beats while the tab is open, regardless of visibility.
 *
 * Options:
 * - `paused`  — when true, no beats are sent (e.g. the idle-logout warning is
 *   showing: the user has been inactive ≥4 min, so the tab must stop signalling
 *   presence). Changes often, so it is read through a ref and never tears down
 *   the interval.
 * - `enabled` — when false, the heartbeat is fully off (e.g. no user logged in).
 *
 * Best-effort by design: all errors are swallowed; the hook must never
 * disturb the UI. Mount it once at the authenticated app root (AppRoutes),
 * gated on auth via `enabled` — unmounting/disabling stops the heartbeat.
 */
import { useEffect, useRef } from 'react';
import { sendPresenceHeartbeat, type PresenceMode } from '../api/sleep';

const DEFAULT_INTERVAL_MS = 45_000;
const CLIENT_ID_KEY = 'baluhost_presence_client_id';

interface UsePresenceHeartbeatOptions {
  /** When true, skip sending heartbeats (idle-logout warning visible). */
  paused?: boolean;
  /** When false, the heartbeat is fully disabled (no user logged in). */
  enabled?: boolean;
}

function getClientId(): string {
  let id = sessionStorage.getItem(CLIENT_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(CLIENT_ID_KEY, id);
  }
  return id;
}

export function usePresenceHeartbeat(options: UsePresenceHeartbeatOptions = {}): void {
  const { paused = false, enabled = true } = options;

  // `paused` flips on every idle warning; keep it in a ref so toggling it does
  // not re-run the effect (which would tear down and recreate the interval).
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    if (!enabled) return;

    let timer: ReturnType<typeof setInterval> | null = null;
    let intervalMs = DEFAULT_INTERVAL_MS;
    let mode: PresenceMode = 'active';
    const clientId = getClientId();

    const beat = async () => {
      if (pausedRef.current) return;
      if (mode === 'active' && document.visibilityState !== 'visible') return;
      try {
        const res = await sendPresenceHeartbeat({ client_id: clientId, client_type: 'web' });
        mode = res.mode;
        const nextMs = Math.max(15, res.heartbeat_interval_seconds) * 1000;
        if (nextMs !== intervalMs) {
          intervalMs = nextMs;
          schedule();
        }
      } catch {
        // best-effort: never disturb the UI
      }
    };

    const schedule = () => {
      if (timer) clearInterval(timer);
      timer = setInterval(() => { void beat(); }, intervalMs);
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') void beat();
    };

    void beat();
    schedule();
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      if (timer) clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [enabled]);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd client && npx vitest run src/__tests__/hooks/usePresenceHeartbeat.test.ts`
Expected: PASS — all 11 tests (8 existing + 3 new) green.

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/usePresenceHeartbeat.ts client/src/__tests__/hooks/usePresenceHeartbeat.test.ts
git commit -m "feat(presence): pause heartbeat via paused/enabled options (#222)"
```

---

## Task 2: Wire `warningVisible` into the hook from `AppRoutes`, remove the call from `Layout`

**Files:**
- Modify: `client/src/App.tsx:11` (add import), `client/src/App.tsx:148-151` (add hook call after `useIdleTimeout`)
- Modify: `client/src/components/Layout.tsx:22` (remove import), `client/src/components/Layout.tsx:123` (remove call)

> No unit test for this task — it is a pure wiring move covered by `tsc -b` (type checking) plus the Task 1 hook tests. Verified by typecheck + full test run in Task 3.

- [ ] **Step 1: Add the import to `App.tsx`**

In `client/src/App.tsx`, directly after line 12 (`import { IdleWarningDialog } from './components/ui/IdleWarningDialog';`), add:

```typescript
import { usePresenceHeartbeat } from './hooks/usePresenceHeartbeat';
```

- [ ] **Step 2: Call the hook in `AppRoutes`**

In `client/src/App.tsx`, inside `function AppRoutes()`, immediately after the `useIdleTimeout({ … })` block (currently ending at line 151) and before the `if (loading) return …` line, add:

```typescript
  usePresenceHeartbeat({ paused: warningVisible, enabled: user !== null });
```

The result reads:

```typescript
  const { warningVisible, secondsRemaining, resetTimer } = useIdleTimeout({
    onLogout: logout,
    enabled: user !== null,
  });

  usePresenceHeartbeat({ paused: warningVisible, enabled: user !== null });

  // Show loading screen while AuthProvider is verifying the stored token
  if (loading) return <LoadingScreen backendReady={true} backendCheckAttempts={0} />;
```

- [ ] **Step 3: Remove the import from `Layout.tsx`**

In `client/src/components/Layout.tsx`, delete line 22:

```typescript
import { usePresenceHeartbeat } from '../hooks/usePresenceHeartbeat';
```

- [ ] **Step 4: Remove the call from `Layout.tsx`**

In `client/src/components/Layout.tsx`, inside `export default function Layout({ children }: LayoutProps)`, delete the line:

```typescript
  usePresenceHeartbeat();
```

(currently line 123, between the `useAuth()` destructure and the `const [mobileMenuOpen, …]` state.)

- [ ] **Step 5: Update the hook doc in `hooks/CLAUDE.md`**

In `client/src/hooks/CLAUDE.md`, find the `usePresenceHeartbeat.ts` row — it lives in the **"Utility Hooks"** table, which is **2-column** (`| Hook | Purpose |`), NOT the 3-column "Data Fetching Hooks" table. The row currently ends with "...fire-and-forget, mounted once in Layout". Replace that row with this 2-column row (do not add an `api/sleep` cell — that would break the table):

```markdown
| `usePresenceHeartbeat.ts` | Presence heartbeat to `/api/system/sleep/presence` while tab visible (blocks auto true-suspend, #214); fire-and-forget, mounted once in `AppRoutes` (auth-gated via `enabled`); paused while the idle-logout warning is visible (#222) |
```

- [ ] **Step 6: Typecheck**

Run: `cd client && npx tsc -b`
Expected: no errors (clean exit). Confirms the import move, the new option usage, and that `usePresenceHeartbeat` has no remaining unused import in `Layout.tsx`.

- [ ] **Step 7: Commit**

```bash
git add client/src/App.tsx client/src/components/Layout.tsx client/src/hooks/CLAUDE.md
git commit -m "feat(presence): mount heartbeat in AppRoutes, pause while idle warning visible (#222)"
```

---

## Task 3: Full verification (lint + typecheck + test suite)

**Files:** none (verification only)

- [ ] **Step 1: Run the full frontend test suite**

Run: `cd client && npx vitest run`
Expected: PASS — entire suite green, including the 12 `usePresenceHeartbeat` tests and the untouched `useIdleTimeout` tests.

- [ ] **Step 2: Typecheck the whole client**

Run: `cd client && npx tsc -b`
Expected: clean exit, no errors.

- [ ] **Step 3: Lint the touched files**

Run: `cd client && npx eslint src/hooks/usePresenceHeartbeat.ts src/App.tsx src/components/Layout.tsx src/__tests__/hooks/usePresenceHeartbeat.test.ts`
Expected: no errors. (Watch for: unused `usePresenceHeartbeat` import left in `Layout.tsx` → would be flagged here.)

- [ ] **Step 4: Manual confirmation (optional, dev mode)**

If verifying live: start dev (`python start_dev.py`), log in, set presence mode to `session` (Sleep settings), open DevTools → Network, filter `presence`. Confirm:
- Heartbeats post every ~45 s.
- When the idle warning dialog appears (or simulate by setting `paused`), POSTs to `/api/system/sleep/presence` stop.
- After clicking *Stay logged in*, heartbeats resume within one interval (≤45 s).

---

## Self-Review Notes

- **Spec coverage:** Issue points 1 (`warningVisible` available to hook → via `AppRoutes` prop), 2 (`if (paused) return` in `beat()` → `if (pausedRef.current) return;`), 4 (tests: skip while paused, resume after) all map to tasks. Point 3 (immediate beat on reset) deliberately deferred — rationale documented above.
- **Type consistency:** `UsePresenceHeartbeatOptions` (`paused?`, `enabled?`) is defined in Task 1 and consumed identically in Task 2 (`{ paused: warningVisible, enabled: user !== null }`). `PresenceMode` imported from `../api/sleep` (unchanged). `warningVisible: boolean` and `user` from existing `useIdleTimeout`/`useAuth` in `AppRoutes`.
- **No placeholders:** every code/command step shows full content.
- **Branch:** execute on a fresh branch cut from `origin/main` (the presence files do not exist on the current `fix/expiry-warner-sleep-catchup` branch).
