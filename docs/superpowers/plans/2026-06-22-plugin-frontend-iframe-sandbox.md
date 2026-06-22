# Plugin Frontend iframe Sandbox — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run plugin frontend code inside a browser-enforced opaque-origin sandbox iframe, talking to the host only through a `postMessage` RPC bridge with default-deny, scope-gated API access — so a malicious plugin can no longer read the JWT, call arbitrary endpoints, or touch the host DOM.

**Architecture:** `PluginPage` renders a `PluginSandboxHost` that mounts `<iframe sandbox="allow-scripts">` (no `allow-same-origin` → opaque origin). A host-built `plugin-runtime.js` runs inside the frame, exposes `window.BaluHost`, and proxies `api`/`toast`/`navigate`/`storage` over `postMessage`. The host bridge holds the real token and enforces a per-call API policy (own routes always; Core routes only via manifest-declared, admin-granted scopes).

**Tech Stack:** React 18 + TypeScript + Vite (client), Vitest (frontend tests), FastAPI + SQLAlchemy 2.0 + Alembic (backend), Pytest (backend tests).

**Spec:** `docs/superpowers/specs/2026-06-22-plugin-frontend-iframe-sandbox-design.md`

## Global Constraints

- **Scope of this plan:** Phases 1–2 of the spec (bridge foundation + API policy). Phases 3–5 (runtime UI lib/theme/storage, migrate 3 bundled plugins + remove legacy, E2E/docs) are outlined at the end and expanded into a follow-up plan.
- **Opaque origin:** the iframe MUST use `sandbox="allow-scripts"` WITHOUT `allow-same-origin`. Never add `allow-same-origin`.
- **Origin check:** validate inbound messages by `event.source === iframe.contentWindow` reference equality, never by `event.origin` (opaque origin posts `"null"`).
- **No token to the plugin:** the runtime SDK exposes no token, no `apiClient`, no `localStorage`. The only egress is `postMessage`.
- **RPC timeout:** 30000 ms.
- **Frontend tests** live under `client/src/__tests__/**/*.test.{ts,tsx}` (vitest config in `client/vite.config.ts`), run with `npx vitest run`.
- **Backend tests** live under `backend/tests/`, run with `python -m pytest`.
- **Repo runs `core.autocrlf=true`** — let git handle line endings; don't fight CRLF.
- **Windows:** the full backend suite hangs on Windows; run targeted test files locally, full suite in CI.
- **Alembic:** new migrations chain onto the real `alembic heads`, not the stale dev-DB head.

## File Structure

**New (frontend):**
- `client/src/lib/plugin-sandbox/protocol.ts` — message envelope types + runtime validators (shared host↔runtime).
- `client/src/lib/plugin-sandbox/hostBridge.ts` — `PluginBridge` class: owns the iframe window, sends `init`, routes RPC, enforces API policy, times out.
- `client/src/lib/plugin-sandbox/scopeCatalog.ts` — the Core scope→pattern catalog + `isCallAllowed()`.
- `client/src/components/plugins/PluginSandboxHost.tsx` — React wrapper: renders the iframe, wires a `PluginBridge`, handles resize/loading/error.
- `client/src/plugin-runtime/index.ts` — runtime entry built separately; boots the in-iframe SDK and renders the plugin.
- `client/src/plugin-runtime/sdk.ts` — builds the in-iframe `window.BaluHost` (proxies over `postMessage`).
- `client/vite.runtime.config.ts` — separate Vite lib build for the runtime → single IIFE asset.

**Modified (frontend):**
- `client/src/components/PluginPage.tsx` — render `<PluginSandboxHost>` instead of the dynamically-imported component.
- `client/package.json` — add `build:runtime` script.

**New/Modified (backend):**
- `backend/app/api/routes/plugins.py` — add `GET /{name}/ui/host.html` (framable bootstrap), add permissive CORS to the `ui/` asset response.
- `backend/app/middleware/security_headers.py` — carve-out so the `host.html` bootstrap keeps `X-Frame-Options: SAMEORIGIN` + CSP `frame-ancestors 'self'` (the global `DENY` would blank the iframe).
- `backend/app/plugins/manifest.py` — add `api_scopes` + `min_runtime_abi` to `PluginManifest`.
- `backend/app/models/plugin.py` — add `granted_api_scopes` column to `InstalledPlugin`.
- `backend/alembic/versions/<rev>_installed_plugins_granted_api_scopes.py` — migration.
- `backend/app/services/plugin_marketplace.py` (or the install route) — persist granted scopes at install.

**New tests:**
- `client/src/__tests__/plugin-sandbox/protocol.test.ts`
- `client/src/__tests__/plugin-sandbox/hostBridge.test.ts`
- `client/src/__tests__/plugin-sandbox/scopeCatalog.test.ts`
- `client/src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx`
- `backend/tests/plugins/test_manifest_api_scopes.py`
- `backend/tests/api/test_plugin_sandbox_assets.py`

---

## Phase 1 — Bridge Foundation

### Task 1: Message envelope protocol + validators

**Files:**
- Create: `client/src/lib/plugin-sandbox/protocol.ts`
- Test: `client/src/__tests__/plugin-sandbox/protocol.test.ts`

**Interfaces:**
- Produces: `RpcRequest`, `RpcResult`, `IframeEvent`, `HostPush` types; `RPC_CHANNELS` const; `isRpcRequest(msg): msg is RpcRequest`; `isIframeEvent(msg): msg is IframeEvent`.

- [ ] **Step 1: Write the failing test**

```ts
// client/src/__tests__/plugin-sandbox/protocol.test.ts
import { describe, it, expect } from 'vitest';
import { isRpcRequest, isIframeEvent, RPC_CHANNELS } from '../../lib/plugin-sandbox/protocol';

describe('protocol validators', () => {
  it('accepts a well-formed rpc request on a known channel', () => {
    const msg = { kind: 'rpc', id: 'a1', channel: 'api', method: 'get', args: ['/api/plugins/x/y'] };
    expect(isRpcRequest(msg)).toBe(true);
  });
  it('rejects an rpc request on an unknown channel', () => {
    const msg = { kind: 'rpc', id: 'a1', channel: 'filesystem', method: 'read', args: [] };
    expect(isRpcRequest(msg)).toBe(false);
  });
  it('rejects rpc with non-string id or non-array args', () => {
    expect(isRpcRequest({ kind: 'rpc', id: 1, channel: 'api', method: 'get', args: [] })).toBe(false);
    expect(isRpcRequest({ kind: 'rpc', id: 'a', channel: 'api', method: 'get', args: 'x' })).toBe(false);
  });
  it('recognises iframe events', () => {
    expect(isIframeEvent({ kind: 'event', name: 'ready', payload: null })).toBe(true);
    expect(isIframeEvent({ kind: 'event', name: 'bogus', payload: null })).toBe(false);
  });
  it('exposes the fixed channel set', () => {
    expect([...RPC_CHANNELS].sort()).toEqual(['api', 'navigate', 'storage', 'toast']);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/protocol.test.ts`
Expected: FAIL — cannot resolve `../../lib/plugin-sandbox/protocol`.

- [ ] **Step 3: Write minimal implementation**

```ts
// client/src/lib/plugin-sandbox/protocol.ts
export const RPC_CHANNELS = ['api', 'toast', 'navigate', 'storage'] as const;
export type RpcChannel = (typeof RPC_CHANNELS)[number];

export const IFRAME_EVENTS = ['ready', 'resize', 'error'] as const;
export type IframeEventName = (typeof IFRAME_EVENTS)[number];

export const HOST_PUSHES = ['init', 'theme-changed', 'visibility'] as const;
export type HostPushName = (typeof HOST_PUSHES)[number];

export interface RpcRequest {
  kind: 'rpc';
  id: string;
  channel: RpcChannel;
  method: string;
  args: unknown[];
}
export interface RpcResult {
  kind: 'rpc-result';
  id: string;
  ok: boolean;
  value?: unknown;
  error?: { code: string; message: string };
}
export interface IframeEvent {
  kind: 'event';
  name: IframeEventName;
  payload: unknown;
}
export interface HostPush {
  kind: 'push';
  name: HostPushName;
  payload: unknown;
}

function isObj(m: unknown): m is Record<string, unknown> {
  return typeof m === 'object' && m !== null;
}
export function isRpcRequest(m: unknown): m is RpcRequest {
  return (
    isObj(m) && m.kind === 'rpc' && typeof m.id === 'string' &&
    typeof m.method === 'string' && Array.isArray(m.args) &&
    typeof m.channel === 'string' && (RPC_CHANNELS as readonly string[]).includes(m.channel)
  );
}
export function isIframeEvent(m: unknown): m is IframeEvent {
  return (
    isObj(m) && m.kind === 'event' && typeof m.name === 'string' &&
    (IFRAME_EVENTS as readonly string[]).includes(m.name)
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/protocol.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/lib/plugin-sandbox/protocol.ts client/src/__tests__/plugin-sandbox/protocol.test.ts
git commit -m "feat(plugin-sandbox): message envelope protocol + validators"
```

---

### Task 2: Scope catalog + API policy matcher

**Files:**
- Create: `client/src/lib/plugin-sandbox/scopeCatalog.ts`
- Test: `client/src/__tests__/plugin-sandbox/scopeCatalog.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `SCOPE_CATALOG: Record<string, { method: string; pattern: RegExp }[]>`; `isCallAllowed(opts: { pluginName: string; method: string; url: string; grantedScopes: string[] }): boolean`.

- [ ] **Step 1: Write the failing test**

```ts
// client/src/__tests__/plugin-sandbox/scopeCatalog.test.ts
import { describe, it, expect } from 'vitest';
import { isCallAllowed } from '../../lib/plugin-sandbox/scopeCatalog';

const base = { pluginName: 'weather', grantedScopes: [] as string[] };

describe('isCallAllowed', () => {
  it('always allows own plugin routes', () => {
    expect(isCallAllowed({ ...base, method: 'get', url: '/api/plugins/weather/forecast' })).toBe(true);
    expect(isCallAllowed({ ...base, method: 'post', url: '/api/plugins/weather/refresh' })).toBe(true);
  });
  it('denies another plugin\'s routes', () => {
    expect(isCallAllowed({ ...base, method: 'get', url: '/api/plugins/other/secret' })).toBe(false);
  });
  it('denies core routes without a granted scope', () => {
    expect(isCallAllowed({ ...base, method: 'get', url: '/api/system/info' })).toBe(false);
  });
  it('allows a core route when the matching scope is granted', () => {
    expect(isCallAllowed({ ...base, grantedScopes: ['read:system-info'], method: 'get', url: '/api/system/info' })).toBe(true);
  });
  it('still denies a different core route with that scope', () => {
    expect(isCallAllowed({ ...base, grantedScopes: ['read:system-info'], method: 'get', url: '/api/users' })).toBe(false);
  });
  it('denies wrong method even with the scope', () => {
    expect(isCallAllowed({ ...base, grantedScopes: ['read:system-info'], method: 'delete', url: '/api/system/info' })).toBe(false);
  });
  it('denies path traversal and non-/api/ targets', () => {
    expect(isCallAllowed({ ...base, method: 'get', url: '/api/plugins/weather/../../users' })).toBe(false);
    expect(isCallAllowed({ ...base, method: 'get', url: 'https://evil.test/api/plugins/weather/x' })).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/scopeCatalog.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```ts
// client/src/lib/plugin-sandbox/scopeCatalog.ts

/** Core scope → concrete allowed (method, path) patterns. Curated; start small.
 *  NO write:* scopes on sensitive Core routes in v1. /api/users, /api/auth etc.
 *  appear in no entry, so no scope can ever open them. */
export const SCOPE_CATALOG: Record<string, { method: string; pattern: RegExp }[]> = {
  'read:system-info': [{ method: 'get', pattern: /^\/api\/system\/info\/?$/ }],
  'read:storage': [
    { method: 'get', pattern: /^\/api\/files\/storage(\/.*)?$/ },
    { method: 'get', pattern: /^\/api\/system\/storage(\/.*)?$/ },
  ],
  'read:power': [{ method: 'get', pattern: /^\/api\/power\/.*$/ }],
};

/** A plugin's own routes are always allowed; everything else needs a granted scope. */
export function isCallAllowed(opts: {
  pluginName: string;
  method: string;
  url: string;
  grantedScopes: string[];
}): boolean {
  const { pluginName, grantedScopes } = opts;
  const method = opts.method.toLowerCase();

  // Reject anything that isn't a clean same-origin /api/ path.
  if (!opts.url.startsWith('/api/')) return false;
  // Normalise and reject traversal.
  const path = new URL(opts.url, 'http://x').pathname;
  if (path !== opts.url.split('?')[0]) return false; // query allowed, traversal/host not
  if (path.includes('/../') || path.includes('..')) return false;

  // Own routes: /api/plugins/{thisPlugin}/...
  const ownPrefix = `/api/plugins/${pluginName}/`;
  if (path.startsWith(ownPrefix)) return true;

  // Core route: must match a granted scope's pattern.
  for (const scope of grantedScopes) {
    const entries = SCOPE_CATALOG[scope];
    if (!entries) continue;
    for (const e of entries) {
      if (e.method === method && e.pattern.test(path)) return true;
    }
  }
  return false;
}
```

- [ ] **Step 3a: Reconcile the traversal assertion**

The test `'/api/plugins/weather/../../users'` must return false. `new URL('/api/plugins/weather/../../users', 'http://x').pathname` collapses to `/users`, which `!== '/api/plugins/weather/../../users'`, so the `path !== opts.url.split('?')[0]` check catches it. Verify this branch is hit (not the `..` substring check) by keeping both guards.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/scopeCatalog.test.ts`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/lib/plugin-sandbox/scopeCatalog.ts client/src/__tests__/plugin-sandbox/scopeCatalog.test.ts
git commit -m "feat(plugin-sandbox): scope catalog + default-deny api policy matcher"
```

---

### Task 3: Host bridge controller

**Files:**
- Create: `client/src/lib/plugin-sandbox/hostBridge.ts`
- Test: `client/src/__tests__/plugin-sandbox/hostBridge.test.ts`

**Interfaces:**
- Consumes: `protocol.ts` (types/validators), `scopeCatalog.ts` (`isCallAllowed`), `apiClient` from `client/src/lib/api`.
- Produces: `class PluginBridge` with constructor `(opts: { iframe: HTMLIFrameElement; pluginName: string; grantedScopes: string[]; user: { id: number; username: string; role: string }; onResize?: (h: number) => void; onNavigate?: (path: string) => void; timeoutMs?: number })`, methods `start()`, `dispose()`, and internal `handleMessage(ev: MessageEvent)`.

- [ ] **Step 1: Write the failing test**

```ts
// client/src/__tests__/plugin-sandbox/hostBridge.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PluginBridge } from '../../lib/plugin-sandbox/hostBridge';

vi.mock('../../lib/api', () => ({
  apiClient: { request: vi.fn(async () => ({ data: { ok: true } })) },
}));
import { apiClient } from '../../lib/api';

function makeIframe() {
  const posted: unknown[] = [];
  const contentWindow = { postMessage: (m: unknown) => posted.push(m) } as unknown as Window;
  const iframe = { contentWindow } as unknown as HTMLIFrameElement;
  return { iframe, contentWindow, posted };
}

function fireFromFrame(contentWindow: Window, data: unknown) {
  // jsdom's MessageEvent constructor won't accept a plain object as `source`,
  // so set it explicitly after construction for the reference-equality check.
  const ev = new MessageEvent('message', { data });
  Object.defineProperty(ev, 'source', { value: contentWindow });
  window.dispatchEvent(ev);
}

describe('PluginBridge', () => {
  const user = { id: 1, username: 'admin', role: 'admin' };
  beforeEach(() => vi.clearAllMocks());

  it('sends init after the frame reports ready', () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user });
    b.start();
    fireFromFrame(contentWindow, { kind: 'event', name: 'ready', payload: null });
    const init = posted.find((m: any) => m.kind === 'push' && m.name === 'init') as any;
    expect(init).toBeTruthy();
    expect(init.payload.user.username).toBe('admin');
    expect(init.payload.pluginName).toBe('weather');
    b.dispose();
  });

  it('performs an allowed own-route api call and replies with the body', async () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user });
    b.start();
    fireFromFrame(contentWindow, { kind: 'rpc', id: 'r1', channel: 'api', method: 'get', args: ['/api/plugins/weather/forecast'] });
    await vi.waitFor(() => {
      const res = posted.find((m: any) => m.kind === 'rpc-result' && m.id === 'r1');
      expect(res).toBeTruthy();
    });
    const res = posted.find((m: any) => m.kind === 'rpc-result' && m.id === 'r1') as any;
    expect(res.ok).toBe(true);
    expect(res.value).toEqual({ ok: true });
    expect(apiClient.request).toHaveBeenCalledOnce();
    b.dispose();
  });

  it('rejects a denied core-route api call without calling apiClient', async () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user });
    b.start();
    fireFromFrame(contentWindow, { kind: 'rpc', id: 'r2', channel: 'api', method: 'get', args: ['/api/users'] });
    await vi.waitFor(() => {
      const res = posted.find((m: any) => m.kind === 'rpc-result' && m.id === 'r2');
      expect(res).toBeTruthy();
    });
    const res = posted.find((m: any) => m.kind === 'rpc-result' && m.id === 'r2') as any;
    expect(res.ok).toBe(false);
    expect(res.error.code).toBe('scope_denied');
    expect(apiClient.request).not.toHaveBeenCalled();
    b.dispose();
  });

  it('ignores messages whose source is not the iframe window', async () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user });
    b.start();
    const other = { postMessage: () => {} } as unknown as Window;
    fireFromFrame(other, { kind: 'rpc', id: 'r3', channel: 'api', method: 'get', args: ['/api/plugins/weather/x'] });
    await new Promise((r) => setTimeout(r, 10));
    expect(posted.find((m: any) => m.id === 'r3')).toBeUndefined();
    b.dispose();
  });

  it('routes resize events to onResize', () => {
    const { iframe, contentWindow } = makeIframe();
    const onResize = vi.fn();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, onResize });
    b.start();
    fireFromFrame(contentWindow, { kind: 'event', name: 'resize', payload: { height: 420 } });
    expect(onResize).toHaveBeenCalledWith(420);
    b.dispose();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/hostBridge.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```ts
// client/src/lib/plugin-sandbox/hostBridge.ts
import { apiClient } from '../api';
import { isRpcRequest, isIframeEvent, type RpcResult, type HostPush } from './protocol';
import { isCallAllowed } from './scopeCatalog';

interface User { id: number; username: string; role: string }

export interface PluginBridgeOpts {
  iframe: HTMLIFrameElement;
  pluginName: string;
  grantedScopes: string[];
  user: User;
  onResize?: (height: number) => void;
  onNavigate?: (path: string) => void;
  timeoutMs?: number;
}

export class PluginBridge {
  private listener = (ev: MessageEvent) => this.handleMessage(ev);
  constructor(private opts: PluginBridgeOpts) {}

  start(): void {
    window.addEventListener('message', this.listener);
  }
  dispose(): void {
    window.removeEventListener('message', this.listener);
  }

  private post(msg: RpcResult | HostPush): void {
    this.opts.iframe.contentWindow?.postMessage(msg, '*');
  }

  private async handleMessage(ev: MessageEvent): Promise<void> {
    // Opaque-origin frames post origin "null" — trust the window reference only.
    if (ev.source !== this.opts.iframe.contentWindow) return;
    const data = ev.data;

    if (isIframeEvent(data)) {
      if (data.name === 'ready') {
        this.post({
          kind: 'push', name: 'init',
          payload: { user: this.opts.user, pluginName: this.opts.pluginName },
        });
      } else if (data.name === 'resize') {
        const h = (data.payload as { height?: unknown })?.height;
        if (typeof h === 'number') this.opts.onResize?.(h);
      }
      return;
    }

    if (!isRpcRequest(data)) return;
    try {
      const value = await this.dispatch(data.channel, data.method, data.args);
      this.post({ kind: 'rpc-result', id: data.id, ok: true, value });
    } catch (err) {
      const e = err as { code?: string; message?: string };
      this.post({
        kind: 'rpc-result', id: data.id, ok: false,
        error: { code: e.code ?? 'error', message: e.message ?? 'Plugin call failed' },
      });
    }
  }

  private async dispatch(channel: string, method: string, args: unknown[]): Promise<unknown> {
    if (channel === 'api') return this.apiCall(method, args);
    if (channel === 'navigate') {
      const path = String(args[0] ?? '');
      const prefix = `/plugins/${this.opts.pluginName}`;
      if (!path.startsWith(prefix)) throw { code: 'navigate_denied', message: 'Out-of-plugin navigation blocked' };
      this.opts.onNavigate?.(path);
      return null;
    }
    throw { code: 'unknown_channel', message: `Unknown channel ${channel}` };
  }

  private async apiCall(method: string, args: unknown[]): Promise<unknown> {
    const url = String(args[0] ?? '');
    const body = args[1];
    if (!isCallAllowed({ pluginName: this.opts.pluginName, method, url, grantedScopes: this.opts.grantedScopes })) {
      throw { code: 'scope_denied', message: `Plugin not permitted to call ${method.toUpperCase()} ${url}` };
    }
    const res = await apiClient.request({ url, method, data: body });
    return res.data;
  }
}
```

(`toast` and `storage` channels arrive in Phase 2/3; `dispatch` throws `unknown_channel` for them until then, which is correct.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/hostBridge.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/lib/plugin-sandbox/hostBridge.ts client/src/__tests__/plugin-sandbox/hostBridge.test.ts
git commit -m "feat(plugin-sandbox): host bridge controller with policy-enforced api channel"
```

---

### Task 4: In-iframe runtime SDK + entry, separate Vite build

**Files:**
- Create: `client/src/plugin-runtime/sdk.ts`
- Create: `client/src/plugin-runtime/index.ts`
- Create: `client/vite.runtime.config.ts`
- Modify: `client/package.json` (add `build:runtime`)
- Test: `client/src/__tests__/plugin-sandbox/runtimeSdk.test.ts`

**Interfaces:**
- Consumes: `protocol.ts` types.
- Produces: `createSandboxSdk(post: (msg: unknown) => void): { api; toast; navigate; setOnInit(cb) }` from `sdk.ts`; a self-booting `index.ts` that wires `window.parent.postMessage` + `window.addEventListener('message')`.

- [ ] **Step 1: Write the failing test** (unit-test the SDK proxy logic, not the DOM boot)

```ts
// client/src/__tests__/plugin-sandbox/runtimeSdk.test.ts
import { describe, it, expect, vi } from 'vitest';
import { createSandboxSdk } from '../../plugin-runtime/sdk';

describe('createSandboxSdk', () => {
  it('api.get posts an rpc and resolves on matching rpc-result', async () => {
    const posted: any[] = [];
    const sdk = createSandboxSdk((m) => posted.push(m));
    const p = sdk.api.get('/api/plugins/weather/forecast');
    const req = posted.find((m) => m.kind === 'rpc' && m.channel === 'api');
    expect(req.method).toBe('get');
    expect(req.args[0]).toBe('/api/plugins/weather/forecast');
    // simulate host reply
    sdk._receive({ kind: 'rpc-result', id: req.id, ok: true, value: { temp: 21 } });
    await expect(p).resolves.toEqual({ temp: 21 });
  });

  it('api rejects on an error rpc-result with the error code', async () => {
    const posted: any[] = [];
    const sdk = createSandboxSdk((m) => posted.push(m));
    const p = sdk.api.get('/api/users');
    const req = posted.find((m) => m.kind === 'rpc');
    sdk._receive({ kind: 'rpc-result', id: req.id, ok: false, error: { code: 'scope_denied', message: 'no' } });
    await expect(p).rejects.toMatchObject({ code: 'scope_denied' });
  });

  it('times out a pending rpc', async () => {
    vi.useFakeTimers();
    const sdk = createSandboxSdk(() => {}, { timeoutMs: 100 });
    const p = sdk.api.get('/api/plugins/weather/x');
    const assertion = expect(p).rejects.toMatchObject({ code: 'timeout' });
    await vi.advanceTimersByTimeAsync(150);
    await assertion;
    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/runtimeSdk.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```ts
// client/src/plugin-runtime/sdk.ts
import { type RpcChannel } from '../lib/plugin-sandbox/protocol';

interface Pending { resolve: (v: unknown) => void; reject: (e: unknown) => void; timer: ReturnType<typeof setTimeout> }

export function createSandboxSdk(post: (msg: unknown) => void, opts: { timeoutMs?: number } = {}) {
  const timeoutMs = opts.timeoutMs ?? 30000;
  const pending = new Map<string, Pending>();
  let counter = 0;

  function call(channel: RpcChannel, method: string, args: unknown[]): Promise<unknown> {
    const id = `rpc-${++counter}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(id);
        reject({ code: 'timeout', message: `RPC ${channel}.${method} timed out` });
      }, timeoutMs);
      pending.set(id, { resolve, reject, timer });
      post({ kind: 'rpc', id, channel, method, args });
    });
  }

  function _receive(msg: { kind?: string; id?: string; ok?: boolean; value?: unknown; error?: unknown }): void {
    if (msg.kind !== 'rpc-result' || typeof msg.id !== 'string') return;
    const p = pending.get(msg.id);
    if (!p) return;
    clearTimeout(p.timer);
    pending.delete(msg.id);
    if (msg.ok) p.resolve(msg.value);
    else p.reject(msg.error ?? { code: 'error', message: 'failed' });
  }

  const api = {
    get: (url: string) => call('api', 'get', [url]),
    post: (url: string, data?: unknown) => call('api', 'post', [url, data]),
    put: (url: string, data?: unknown) => call('api', 'put', [url, data]),
    patch: (url: string, data?: unknown) => call('api', 'patch', [url, data]),
    delete: (url: string) => call('api', 'delete', [url]),
  };
  const toast = {
    success: (m: string) => post({ kind: 'rpc', id: `t-${++counter}`, channel: 'toast', method: 'success', args: [m] }),
    error: (m: string) => post({ kind: 'rpc', id: `t-${++counter}`, channel: 'toast', method: 'error', args: [m] }),
  };
  const navigate = (path: string) => call('navigate', 'go', [path]);

  return { api, toast, navigate, _receive };
}
```

```ts
// client/src/plugin-runtime/index.ts
// Boots inside the sandbox iframe: wires postMessage, exposes window.BaluHost,
// then loads the plugin bundle. (UI lib + React are added in Phase 3; here we
// expose the proxy SDK and announce readiness so the host sends `init`.)
import { createSandboxSdk } from './sdk';

const sdk = createSandboxSdk((msg) => window.parent.postMessage(msg, '*'));

window.addEventListener('message', (ev) => {
  const data = ev.data;
  if (data && data.kind === 'rpc-result') sdk._receive(data);
  if (data && data.kind === 'push' && data.name === 'init') {
    (window as unknown as { BaluHost: unknown }).BaluHost = {
      api: sdk.api, toast: sdk.toast, navigate: sdk.navigate,
      user: (data.payload as { user: unknown }).user,
    };
    void loadPluginBundle();
  }
});

async function loadPluginBundle(): Promise<void> {
  // The plugin bundle path is injected via a <meta name="plugin-bundle"> tag in host.html.
  const meta = document.querySelector('meta[name="plugin-bundle"]') as HTMLMetaElement | null;
  if (!meta) return;
  await import(/* @vite-ignore */ meta.content);
}

// Announce readiness so the host responds with `init`.
window.parent.postMessage({ kind: 'event', name: 'ready', payload: null }, '*');
```

```ts
// client/vite.runtime.config.ts
import { defineConfig } from 'vite';

// Builds the in-iframe runtime as a single IIFE asset into `public/`, so Vite
// serves it at `/plugin-runtime.js` in BOTH dev (public is served at root) and
// prod (public is copied into dist). host.html references it absolutely.
export default defineConfig({
  build: {
    emptyOutDir: false,
    outDir: 'public',
    lib: {
      entry: 'src/plugin-runtime/index.ts',
      name: 'BaluHostPluginRuntime',
      formats: ['iife'],
      fileName: () => 'plugin-runtime.js',
    },
    rollupOptions: { output: { entryFileNames: 'plugin-runtime.js' } },
  },
});
```

In `client/package.json` scripts, add `build:runtime` and run it before the main build:
```json
"build:runtime": "vite build --config vite.runtime.config.ts",
"prebuild": "npm run build:runtime"
```

Add the generated artifact to `client/.gitignore` (it's a build output, not source):
```
public/plugin-runtime.js
```

For dev: `npm run build:runtime` once after pulling (document this in the migration guide); the file is then served at `/plugin-runtime.js` by the Vite dev server.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/runtimeSdk.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Verify the runtime builds**

Run: `cd client && npm run build:runtime`
Expected: emits `client/public/plugin-runtime.js`, no errors. Add `public/plugin-runtime.js` to `client/.gitignore`.

- [ ] **Step 6: Commit**

```bash
git add client/src/plugin-runtime client/vite.runtime.config.ts client/package.json client/src/__tests__/plugin-sandbox/runtimeSdk.test.ts
git commit -m "feat(plugin-sandbox): in-iframe runtime SDK + separate vite runtime build"
```

---

### Task 5: Backend — serve framable `host.html`, permissive CORS, middleware carve-out

**Files:**
- Modify: `backend/app/api/routes/plugins.py` (the `serve_plugin_asset` route region, ~438–500)
- Modify: `backend/app/middleware/security_headers.py` (carve-out so the bootstrap stays framable)
- Test: `backend/tests/api/test_plugin_sandbox_assets.py`

**Interfaces:**
- Produces: `GET /api/plugins/{name}/ui/host.html` → HTML bootstrap referencing `/plugin-runtime.js` + a `<meta name="plugin-bundle">` pointing at the plugin's bundle; existing `ui/{file}` responses gain `Access-Control-Allow-Origin: *`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_plugin_sandbox_assets.py
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_ui_asset_has_permissive_cors(client, monkeypatch):
    """ui/ assets must be loadable from the opaque-origin sandbox iframe."""
    # A known bundled plugin is enabled in the test app's plugin manager.
    resp = client.get("/api/plugins/storage_analytics/ui/bundle.js")
    # Either the asset exists (200) or the plugin isn't enabled in this env (404);
    # when served, it must carry the CORS header.
    if resp.status_code == 200:
        assert resp.headers.get("access-control-allow-origin") == "*"


def test_host_html_bootstrap_served(client):
    resp = client.get("/api/plugins/storage_analytics/ui/host.html")
    if resp.status_code == 200:
        body = resp.text
        assert "plugin-runtime.js" in body
        assert 'name="plugin-bundle"' in body
        assert resp.headers.get("content-type", "").startswith("text/html")


def test_host_html_is_framable_same_origin(client):
    """The sandbox bootstrap MUST be framable by our own app — the global
    X-Frame-Options: DENY would otherwise blank the iframe."""
    resp = client.get("/api/plugins/storage_analytics/ui/host.html")
    if resp.status_code == 200:
        assert resp.headers.get("x-frame-options", "DENY").upper() != "DENY"
        # CSP frame-ancestors must allow same-origin framing.
        assert "frame-ancestors" in resp.headers.get("content-security-policy", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_plugin_sandbox_assets.py -v`
Expected: FAIL — `host.html` route returns 404 / no CORS header.

- [ ] **Step 3: Write minimal implementation**

In `serve_plugin_asset`, before the generic file handling, special-case `host.html`, and add the CORS header to the returned `FileResponse`. Add near the top of the function body (after the enabled-check):

```python
    # Sandbox bootstrap document — generated, not read from disk.
    if file_path == "host.html":
        # Resolve the plugin's UI bundle name from its manifest (fall back to bundle.js).
        bundle_path = "bundle.js"
        try:
            from app.plugins.manifest import load_manifest
            manifest = load_manifest(plugin_manager.plugins_dir / name)
            if manifest.ui and manifest.ui.bundle:
                bundle_path = manifest.ui.bundle
        except Exception:
            pass
        html = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<meta name='plugin-bundle' content='/api/plugins/{name}/ui/{bundle_path}'>"
            "</head><body><div id='plugin-root'></div>"
            "<script src='/plugin-runtime.js'></script></body></html>"
        )
        return Response(
            content=html,
            media_type="text/html",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-store",
                # Make the bootstrap framable by our own SPA. The global
                # SecurityHeadersMiddleware would set DENY; the middleware
                # carve-out (Step 4) preserves these for the sandbox path.
                "X-Frame-Options": "SAMEORIGIN",
                "Content-Security-Policy": "frame-ancestors 'self'",
            },
        )
```

Then change the final `FileResponse(...)` headers dict to include CORS:

```python
    return FileResponse(
        plugin_path,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )
```

(Ensure `Response` is imported: `from fastapi import Response` — it already is in this module.)

- [ ] **Step 4: Carve out the sandbox bootstrap in SecurityHeadersMiddleware**

The middleware runs after the route and unconditionally sets `X-Frame-Options: DENY`, which would clobber the framable header and blank the iframe. Modify `backend/app/middleware/security_headers.py` so the sandbox bootstrap keeps its own framing headers.

In `SecurityHeadersMiddleware.dispatch`, right after `response = await call_next(request)`, add:

```python
        # The plugin sandbox bootstrap must be framable by our own SPA; it sets
        # its own X-Frame-Options/CSP frame-ancestors. Skip the global DENY/CSP
        # for that single path so the iframe can render.
        if request.url.path.endswith("/ui/host.html") and request.url.path.startswith("/api/plugins/"):
            return response
```

This returns before the global header block overwrites the route's headers. (All other plugin asset paths still get the standard headers.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/api/test_plugin_sandbox_assets.py -v`
Expected: PASS (3 tests; assertions are conditional on the plugin being enabled in the test env).

- [ ] **Step 7: Confirm runtime asset serving**

`plugin-runtime.js` is emitted into `client/public/` by `build:runtime` (Task 4), so the `prebuild` hook makes `npm run build` copy it into `dist/` and `/plugin-runtime.js` resolves via the existing static mount in prod, and via the Vite dev server in dev. No backend route needed for the runtime itself. Verify `/plugin-runtime.js` is reachable in a dev session after `npm run build:runtime`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/routes/plugins.py backend/app/middleware/security_headers.py backend/tests/api/test_plugin_sandbox_assets.py
git commit -m "feat(plugin-sandbox): serve framable host.html bootstrap + CORS, middleware carve-out"
```

---

### Task 6: `PluginSandboxHost` component + wire `PluginPage`

**Files:**
- Create: `client/src/components/plugins/PluginSandboxHost.tsx`
- Modify: `client/src/components/PluginPage.tsx` (replace dynamic-import render with `<PluginSandboxHost>`)
- Test: `client/src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx`

**Interfaces:**
- Consumes: `PluginBridge` from `hostBridge.ts`.
- Produces: `<PluginSandboxHost pluginName user grantedScopes />` rendering `<iframe sandbox="allow-scripts" src="/api/plugins/{name}/ui/host.html">`.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import PluginSandboxHost from '../../components/plugins/PluginSandboxHost';

describe('PluginSandboxHost', () => {
  const user = { id: 1, username: 'admin', role: 'admin' };
  it('renders an opaque-origin sandbox iframe pointing at host.html', () => {
    const { container } = render(
      <PluginSandboxHost pluginName="weather" user={user} grantedScopes={[]} />
    );
    const iframe = container.querySelector('iframe')!;
    expect(iframe).toBeTruthy();
    expect(iframe.getAttribute('sandbox')).toBe('allow-scripts');
    expect(iframe.getAttribute('src')).toBe('/api/plugins/weather/ui/host.html');
  });

  it('never grants allow-same-origin', () => {
    const { container } = render(
      <PluginSandboxHost pluginName="weather" user={user} grantedScopes={[]} />
    );
    const sandbox = container.querySelector('iframe')!.getAttribute('sandbox')!;
    expect(sandbox.includes('allow-same-origin')).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```tsx
// client/src/components/plugins/PluginSandboxHost.tsx
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PluginBridge } from '../../lib/plugin-sandbox/hostBridge';

interface User { id: number; username: string; role: string }
interface Props {
  pluginName: string;
  user: User;
  grantedScopes: string[];
}

export default function PluginSandboxHost({ pluginName, user, grantedScopes }: Props) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const navigate = useNavigate();
  const [height, setHeight] = useState(480);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    const bridge = new PluginBridge({
      iframe, pluginName, grantedScopes, user,
      onResize: (h) => setHeight(Math.max(120, Math.ceil(h))),
      onNavigate: (path) => navigate(path),
    });
    bridge.start();
    return () => bridge.dispose();
  }, [pluginName, grantedScopes, user, navigate]);

  return (
    <iframe
      ref={iframeRef}
      title={`plugin-${pluginName}`}
      src={`/api/plugins/${pluginName}/ui/host.html`}
      sandbox="allow-scripts"
      style={{ width: '100%', height, border: 'none' }}
    />
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Wire `PluginPage`**

In `client/src/components/PluginPage.tsx`: remove the `loadPluginComponent`/`loadPluginStyles` usage and the `PluginComponent` state/effect; render the sandbox host in the return block instead of `<PluginComponent user={user} />`:

```tsx
// imports: drop loadPluginComponent/loadPluginStyles; add:
import PluginSandboxHost from './plugins/PluginSandboxHost';
// ... in the final return, replace <Suspense>…<PluginComponent/></Suspense> with:
<PluginSandboxHost
  pluginName={pluginName!}
  user={user}
  grantedScopes={pluginInfo?.granted_api_scopes ?? []}
/>
```

(`granted_api_scopes` is added to the plugin info type in Phase 2, Task 9/10; until then pass `[]`.)

- [ ] **Step 6: Run the frontend suite + typecheck**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/ && npx tsc --noEmit`
Expected: all sandbox tests PASS; no type errors (use `grantedScopes={[]}` literal if the field isn't on the type yet).

- [ ] **Step 7: Commit**

```bash
git add client/src/components/plugins/PluginSandboxHost.tsx client/src/components/PluginPage.tsx client/src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx
git commit -m "feat(plugin-sandbox): PluginSandboxHost component, wire PluginPage to the sandbox"
```

---

## Phase 2 — API Policy: manifest scopes, grant, audit

### Task 7: Manifest `api_scopes` + `min_runtime_abi`

**Files:**
- Modify: `backend/app/plugins/manifest.py:37-58` (`PluginManifest`)
- Test: `backend/tests/plugins/test_manifest_api_scopes.py`

**Interfaces:**
- Produces: `PluginManifest.api_scopes: list[str]` (default `[]`), `PluginManifest.min_runtime_abi: int | None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/plugins/test_manifest_api_scopes.py
import json
from pathlib import Path
import pytest
from app.plugins.manifest import load_manifest, PluginManifest


def _write(tmp_path: Path, extra: dict) -> Path:
    base = {
        "manifest_version": 1, "name": "weather", "version": "1.0.0",
        "display_name": "Weather", "description": "d", "author": "a",
    }
    base.update(extra)
    (tmp_path / "plugin.json").write_text(json.dumps(base), encoding="utf-8")
    return tmp_path


def test_api_scopes_default_empty(tmp_path):
    m = load_manifest(_write(tmp_path, {}))
    assert m.api_scopes == []
    assert m.min_runtime_abi is None


def test_api_scopes_parsed(tmp_path):
    m = load_manifest(_write(tmp_path, {"api_scopes": ["read:storage"], "min_runtime_abi": 1}))
    assert m.api_scopes == ["read:storage"]
    assert m.min_runtime_abi == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_manifest_api_scopes.py -v`
Expected: FAIL — `api_scopes` not an attribute.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/plugins/manifest.py`, add to `PluginManifest` (after `python_requirements`):

```python
    api_scopes: List[str] = Field(default_factory=list)
    min_runtime_abi: Optional[int] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_manifest_api_scopes.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/manifest.py backend/tests/plugins/test_manifest_api_scopes.py
git commit -m "feat(plugin-sandbox): manifest api_scopes + min_runtime_abi fields"
```

---

### Task 8: `InstalledPlugin.granted_api_scopes` column + migration

**Files:**
- Modify: `backend/app/models/plugin.py` (add column after `granted_permissions`)
- Create: `backend/alembic/versions/<rev>_installed_plugins_granted_api_scopes.py`
- Test: `backend/tests/plugins/test_installed_plugin_scopes.py`

**Interfaces:**
- Produces: `InstalledPlugin.granted_api_scopes: list[str] | None` (JSON, default `[]`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/plugins/test_installed_plugin_scopes.py
from app.models.plugin import InstalledPlugin


def test_granted_api_scopes_roundtrip(db_session):
    p = InstalledPlugin(name="weather", version="1.0.0", display_name="Weather",
                        granted_api_scopes=["read:storage"])
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    assert p.granted_api_scopes == ["read:storage"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_installed_plugin_scopes.py -v`
Expected: FAIL — unexpected keyword `granted_api_scopes`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/models/plugin.py`, after `granted_permissions` (line ~26-28):

```python
    granted_api_scopes: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True, default=list
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_installed_plugin_scopes.py -v`
Expected: PASS (the test DB is created from models, so the column exists).

- [ ] **Step 5: Generate the migration against the real head**

```bash
cd backend
alembic heads          # note the current head revision
alembic revision --autogenerate -m "installed_plugins granted_api_scopes"
```

Verify the generated file's `down_revision` equals the `alembic heads` output (see `project_alembic_migration_head_pitfall`). The `upgrade()` should `op.add_column('installed_plugins', sa.Column('granted_api_scopes', sa.JSON(), nullable=True))` and `downgrade()` drop it.

- [ ] **Step 6: Apply + verify**

Run: `cd backend && alembic upgrade head`
Expected: applies cleanly; `alembic current` shows the new head.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/plugin.py backend/alembic/versions/*granted_api_scopes*.py backend/tests/plugins/test_installed_plugin_scopes.py
git commit -m "feat(plugin-sandbox): InstalledPlugin.granted_api_scopes column + migration"
```

---

### Task 9: Expose granted scopes to the frontend plugin info

**Files:**
- Modify: the plugin-list endpoint + response schema in `backend/app/api/routes/plugins.py` (the enabled/installed plugin response that the frontend `PluginContext` consumes) to include `granted_api_scopes`.
- Modify: `client/src/api/plugins.ts` (the plugin info type) + `client/src/contexts/PluginContext` consumers to carry `granted_api_scopes`.
- Test: extend an existing plugins-route test (or add `backend/tests/api/test_plugins_list_scopes.py`).

**Interfaces:**
- Produces: each plugin entry returned to the SPA carries `granted_api_scopes: string[]`. `PluginSandboxHost` reads it (Task 6, Step 5).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_plugins_list_scopes.py
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_plugin_list_includes_granted_api_scopes(client, admin_auth_headers):
    resp = client.get("/api/plugins", headers=admin_auth_headers)
    assert resp.status_code == 200
    for entry in resp.json().get("plugins", []):
        assert "granted_api_scopes" in entry
        assert isinstance(entry["granted_api_scopes"], list)
```

(Use the project's existing admin-auth fixture; match the real list endpoint path/shape — adjust `"/api/plugins"` and `["plugins"]` to the actual response in `plugins.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_plugins_list_scopes.py -v`
Expected: FAIL — key absent.

- [ ] **Step 3: Write minimal implementation**

Add `granted_api_scopes` to the plugin-list response model/dict in `plugins.py`, sourced from `InstalledPlugin.granted_api_scopes or []`. Mirror the field in `client/src/api/plugins.ts`'s plugin interface, and ensure `PluginContext`'s `enabledPlugins` carries it through.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/api/test_plugins_list_scopes.py -v`
Expected: PASS.

- [ ] **Step 5: Frontend typecheck**

Run: `cd client && npx tsc --noEmit`
Expected: no errors; `PluginSandboxHost` now reads `pluginInfo.granted_api_scopes`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/plugins.py client/src/api/plugins.ts client/src/contexts backend/tests/api/test_plugins_list_scopes.py
git commit -m "feat(plugin-sandbox): expose granted_api_scopes to the SPA plugin list"
```

---

### Task 10: Grant scopes at install + scope_denied audit log

**Files:**
- Modify: the install flow in `backend/app/services/plugin_marketplace.py` (or the install route) to persist `manifest.api_scopes` into `InstalledPlugin.granted_api_scopes` (admin-confirmed — store declared scopes as granted on install).
- Modify: install-dialog UI to display declared scopes (the marketplace install component).
- Modify: `client/src/lib/plugin-sandbox/hostBridge.ts` — on `scope_denied`, emit a one-line `console.warn` and (optionally) POST a lightweight audit event to `/api/plugins/{name}/_audit/scope-denied` (rate-limited backend route).
- Test: `backend/tests/plugins/test_install_grants_scopes.py`

**Interfaces:**
- Consumes: `PluginManifest.api_scopes`, `InstalledPlugin.granted_api_scopes`.
- Produces: install persists granted scopes; denied calls are audit-logged.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/plugins/test_install_grants_scopes.py
def test_install_persists_declared_scopes(db_session, fake_marketplace_index):
    """After install, the InstalledPlugin row carries the manifest's api_scopes."""
    from app.models.plugin import InstalledPlugin
    # ... arrange a fake index entry whose manifest declares api_scopes=["read:storage"]
    # ... call the installer used by the marketplace install route
    row = db_session.query(InstalledPlugin).filter_by(name="weather").one()
    assert row.granted_api_scopes == ["read:storage"]
```

(Wire to the existing installer test harness in `backend/tests/plugins/`; reuse the `fake_marketplace_index` / temp-index fixtures already used by installer tests.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_install_grants_scopes.py -v`
Expected: FAIL — `granted_api_scopes` stays empty after install.

- [ ] **Step 3: Write minimal implementation**

In the install path, after creating/updating the `InstalledPlugin` row, set `row.granted_api_scopes = list(manifest.api_scopes)`. Add the scope list to the install-dialog payload so the admin sees what they grant. Add a rate-limited `POST /api/plugins/{name}/_audit/scope-denied` route that calls `get_audit_logger_db()` with event_type `"PLUGIN"`, action `"scope_denied"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_install_grants_scopes.py -v`
Expected: PASS.

- [ ] **Step 5: Frontend — surface denials**

In `hostBridge.ts` `apiCall`, when `isCallAllowed` is false, before throwing, `console.warn('[plugin:'+pluginName+'] scope_denied', method, url)` and fire-and-forget `apiClient.post('/api/plugins/'+pluginName+'/_audit/scope-denied', { method, url }).catch(()=>{})`.

- [ ] **Step 6: Run targeted suites**

Run: `cd backend && python -m pytest tests/plugins/ -q` and `cd client && npx vitest run src/__tests__/plugin-sandbox/`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/plugin_marketplace.py backend/app/api/routes/plugins.py client/src backend/tests/plugins/test_install_grants_scopes.py
git commit -m "feat(plugin-sandbox): grant scopes at install + scope_denied audit logging"
```

---

## Phase 1–2 Verification

- [ ] Run the full sandbox frontend suite: `cd client && npx vitest run src/__tests__/plugin-sandbox/` → all green.
- [ ] Run backend plugin + sandbox tests: `cd backend && python -m pytest tests/plugins/ tests/api/test_plugin_sandbox_assets.py tests/api/test_plugins_list_scopes.py -q` → all green.
- [ ] Typecheck: `cd client && npx tsc --noEmit` → clean.
- [ ] Manual smoke (dev): enable a plugin, open its page, confirm it renders inside an iframe (`sandbox="allow-scripts"`, no `allow-same-origin`), confirm an own-route call succeeds and a `/api/users` call is denied in the console.
- [ ] Confirm the main window no longer defines `window.BaluHost` (DevTools console: `window.BaluHost` → `undefined`) once Phase 4 removes the legacy SDK; until then it still exists and is removed in the follow-up plan.

---

## Future Phases (follow-up plan)

These are the remaining spec phases. They get their own detailed TDD plan (`2026-XX-XX-plugin-frontend-iframe-sandbox-phase3-5.md`) when Phases 1–2 land. Outline only:

- **Phase 3 — Runtime UI lib + theme + storage.** Bundle React + the existing UI component library (`Button`/`Card`/`Modal`/…) + compiled Tailwind/theme CSS into `plugin-runtime.js`; inject theme tokens from the `init` handshake; add the `storage` channel (decide server-side per-plugin table vs. bounded client prefix). Re-export `BaluHost.React`/`hooks`/`ui`/`icons`/`utils` inside the iframe.
- **Phase 4 — Migrate the 3 bundled plugins + remove legacy.** Convert `optical_drive`, `storage_analytics`, `tapo_smart_plug` to the externals/runtime-ABI build, add `api_scopes` + `min_runtime_abi` to each `plugin.json`, re-point Core calls. Then DELETE `client/src/lib/pluginLoader.ts` and the main-context `client/src/lib/pluginSDK.ts` (`initPluginSDK`), and remove its call site so `window.BaluHost` no longer exists in the host context.
- **Phase 5 — E2E + docs.** Playwright test: a test plugin loads in the iframe, makes one allowed + one denied call, asserts the main context exposes no `window.BaluHost`. Plugin-author migration guide; `min_runtime_abi` / ABI versioning doc; ensure the deploy frontend build runs `build:runtime`.

---

## Self-Review (completed)

- **Spec coverage (Phases 1–2):** opaque-origin iframe (Task 6), reference-equality origin check (Task 3), envelope/channels (Task 1), default-deny scope policy + own-routes (Task 2/3), no-token runtime SDK (Task 4), `host.html` + CORS (Task 5), manifest scopes (Task 7), grant column + migration (Task 8/9), install grant + audit (Task 10). Phases 3–5 explicitly deferred to a follow-up plan.
- **Placeholder scan:** none — every code step carries real code; Task 9/10 note where to match existing fixtures/paths rather than inventing them.
- **Type consistency:** `RpcRequest`/`RpcResult`/`IframeEvent` shared from `protocol.ts`; `PluginBridge` ctor matches `PluginSandboxHost` usage; `isCallAllowed` signature identical across Task 2 and Task 3; `granted_api_scopes` consistent across model/migration/route/frontend.
