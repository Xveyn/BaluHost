# Task 6 Report: PluginSandboxHost component + wire PluginPage

## Status
DONE — all steps complete, tests green, tsc clean, committed.

## Commit
SHA: `06352b1b`
Subject: `feat(plugin-sandbox): PluginSandboxHost component, wire PluginPage to the sandbox`

## TDD RED → GREEN

### RED (failing test)
```
npx vitest run src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx
```
Output: FAIL — `Failed to resolve import "../../components/plugins/PluginSandboxHost"` (module not found). Confirmed expected RED state.

### Deviation from brief test code
The brief's test code renders `<PluginSandboxHost>` directly without any provider wrapper. Two issues required deviation:
1. `useNavigate()` (called in the component) throws without a Router context → wrapped renders in `<MemoryRouter>`.
2. `vi.fn().mockImplementation(() => ({...}))` is not constructable → replaced with a proper `class` mock for `PluginBridge` (arrow functions aren't constructors; Vitest 4 enforces this).

These changes preserve the exact assertions; only the test scaffolding changed.

### GREEN
```
npx vitest run src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx
```
Output: 2 passed (2 tests).

## All Sandbox Tests
```
npx vitest run src/__tests__/plugin-sandbox/
```
Output: **5 test files, 22 tests — all passed**.

## TypeScript
```
npx tsc --noEmit
```
Output: (no output — zero errors).

## granted_api_scopes Resolution
The `enabledPlugins` array in `PluginContext` is typed as `PluginUIInfo[]` (from `client/src/api/plugins.ts`). `PluginUIInfo` does NOT have a `granted_api_scopes` field — that's a Phase 2 addition. Per the brief constraint, `grantedScopes={[]}` is used literally with a `// TODO(Phase 2): wire granted_api_scopes from pluginInfo once the field exists on PluginUIInfo` comment in `PluginPage.tsx`. tsc is clean.

## Files Changed
| File | Change |
|---|---|
| `client/src/components/plugins/PluginSandboxHost.tsx` | Created — opaque-origin iframe + PluginBridge wiring with start/dispose cleanup and resize/navigate handlers |
| `client/src/components/PluginPage.tsx` | Modified — removed `loadPluginComponent`/`loadPluginStyles`/`PluginComponent` state+effect+Suspense; now renders `<PluginSandboxHost>` |
| `client/src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx` | Created — 2 tests verifying correct `sandbox="allow-scripts"` and correct src, and verifying `allow-same-origin` is never present |

## Self-Review
- iframe has `sandbox="allow-scripts"` ONLY — no `allow-same-origin`. ✓
- `src` is `/api/plugins/${pluginName}/ui/host.html`. ✓
- Bridge is constructed with `iframe, pluginName, grantedScopes, user, onResize, onNavigate`. ✓
- `bridge.start()` called on mount, `bridge.dispose()` called on unmount. ✓
- `PluginPage.tsx` no longer imports `loadPluginComponent`, `loadPluginStyles`, or uses `PluginComponent` state/effect. ✓
- `pluginLoader.ts` and `pluginSDK.ts` NOT deleted (per constraint). ✓
- tsc clean. ✓
- Tests verify real behavior (actual DOM attributes). ✓

## Concerns
None. The only deviation from the brief's test code (MemoryRouter wrapper + class-style PluginBridge mock) was necessary for the test to run at all in jsdom — the assertions themselves are unchanged.

---

## Review Fix: Stabilize bridge lifecycle (2026-06-22)

### Finding
The `useEffect` dep array `[pluginName, grantedScopes, user, navigate]` caused the bridge to be torn down and recreated on every parent re-render because `grantedScopes` is a new array reference each time (callers pass `[]` literals) and `user` is a new object reference. The isolation model is one bridge per plugin SESSION, not per render.

### Fix
`client/src/components/plugins/PluginSandboxHost.tsx`:
- Derived two stable primitive keys before the effect: `scopesKey = grantedScopes.join(',')` and `userId = user.id`.
- Changed dep array to `[pluginName, scopesKey, userId, navigate]` with `// eslint-disable-next-line react-hooks/exhaustive-deps`.
- The actual `grantedScopes` array and `user` object are still read inside the effect body (so the bridge receives real values, not the derived keys).
- `sandbox="allow-scripts"` (no allow-same-origin) unchanged.

### Regression Test Added
`client/src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx`:
- Added module-level `bridgeConstructorCallCount` and `lastBridgeInstance` trackers, reset in `beforeEach`.
- Added test: `does not recreate the bridge when parent re-renders with a new [] literal (same contents) and same user` — re-renders with a brand-new `[]` literal and asserts constructor called exactly once and `dispose()` not called.

### Commands Run
```
cd client && npx vitest run src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx
```
Result: 3 passed (3 tests) — 2 existing + 1 new regression.

```
npx tsc --noEmit
```
Result: (no output — zero errors).
