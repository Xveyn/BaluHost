# Plugin Frontend Sandbox — Phases 3–5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Track A of plugin sandboxing — ship the in-iframe React+UI runtime with theme + server-backed per-user storage, migrate the two bundled UI plugins, delete the legacy main-context SDK (closing the audit gap), and cover it with E2E + author docs.

**Architecture:** The Phases 1–2 sandbox (`PluginPage → PluginSandboxHost → <iframe sandbox="allow-scripts">` + `PluginBridge` + default-deny scope policy) already exists on `main`. This plan (a) fattens `plugin-runtime.js` into the full `window.BaluHost` surface + compiled CSS + theme tokens, (b) adds a `storage` channel backed by a `plugin_storage` table scoped per `(plugin, user)`, (c) migrates `optical_drive` + `storage_analytics` and deletes `pluginLoader.ts` / `pluginSDK.ts` / `initPluginSDK()`, and (d) adds Playwright + docs.

**Tech Stack:** React 18 + TypeScript + Vite (client), Vitest + Playwright (frontend tests), FastAPI + SQLAlchemy 2.0 + Alembic (backend), Pytest (backend tests).

**Spec:** `docs/superpowers/specs/2026-06-24-plugin-sandbox-phase3-5-design.md`

## Global Constraints

- **Single PR / branch:** `feat/plugin-sandbox-phase3-5` (already checked out off synced `main`).
- **Opaque origin is sacred:** the iframe keeps `sandbox="allow-scripts"` WITHOUT `allow-same-origin`. Never add it.
- **Origin check:** inbound messages validated by `event.source === iframe.contentWindow` reference equality, never `event.origin`.
- **No token in the iframe:** the runtime SDK exposes no token, no `apiClient`, no host `localStorage`. The only egress is `postMessage`.
- **RPC timeout:** 30000 ms (already in `createSandboxSdk`).
- **Storage quota:** value ≤ 64 KB serialized; ≤ 100 keys per `(plugin, user)`.
- **Storage scope:** every storage row is keyed by `(plugin_name, user_id, key)`; a user never reads another user's plugin state.
- **Runtime ABI:** `runtime_abi = 1`. A plugin manifest's `min_runtime_abi` (already a field since Phase 2) greater than the runtime → host shows a clean error, does not load `bundle.js`.
- **Frontend tests:** `client/src/__tests__/**/*.test.{ts,tsx}`, run with `npx vitest run`.
- **Backend tests:** `backend/tests/`, run with `python -m pytest` (targeted files locally; full suite hangs on Windows → CI).
- **Alembic:** new migration's `down_revision` MUST equal the real `alembic heads`, not the stale dev-DB head (see `project_alembic_migration_head_pitfall`).
- **CRLF:** repo runs `core.autocrlf=true` — don't fight line endings.
- **Build outputs `client/public/plugin-runtime.js` and `client/public/plugin-runtime.css` stay gitignored.**

## File Structure

**New (frontend):**
- `client/src/plugin-runtime/surface.ts` — assembles the non-proxy half of `window.BaluHost` (React, hooks, ui, icons, utils). Imported only by the runtime build.
- `client/src/plugin-runtime/runtime.css` — `@tailwind` directives + theme-variable base, compiled into `plugin-runtime.css`.

**Modified (frontend):**
- `client/src/lib/plugin-sandbox/protocol.ts` — add `ThemePayload`, extend init/ready payload typing.
- `client/src/lib/plugin-sandbox/hostBridge.ts` — theme in `init`, `setTheme()`, ABI gate, `storage` dispatch.
- `client/src/plugin-runtime/sdk.ts` — add `storage` proxy.
- `client/src/plugin-runtime/index.ts` — assemble full `window.BaluHost`, apply theme, report `runtime_abi`.
- `client/src/components/plugins/PluginSandboxHost.tsx` — feed theme + `minRuntimeAbi`, push theme changes, error state.
- `client/src/components/PluginPage.tsx` — pass `minRuntimeAbi` from plugin info.
- `client/vite.runtime.config.ts` — emit `plugin-runtime.css` with a fixed name.
- `client/src/main.tsx` — remove `initPluginSDK()` (Phase 4).

**Deleted (frontend, Phase 4):**
- `client/src/lib/pluginLoader.ts`, `client/src/lib/pluginSDK.ts`.

**New (backend):**
- `backend/app/models/plugin_storage.py` — `PluginStorage` model.
- `backend/app/services/plugin_storage_service.py` — quota-checked CRUD helpers.
- `backend/alembic/versions/<rev>_plugin_storage.py` — migration.

**Modified (backend):**
- `backend/app/models/__init__.py` — register `PluginStorage`.
- `backend/app/schemas/plugin.py` — `PluginStorageSetRequest`; add `min_runtime_abi` to the UI-manifest info.
- `backend/app/api/routes/plugins.py` — `_storage` routes; add `<link>` to `host.html`; surface `min_runtime_abi` in the UI manifest.

**Modified (plugins, Phase 4):**
- `backend/app/plugins/installed/storage_analytics/ui/bundle.js`, `.../storage_analytics/plugin.json`
- `backend/app/plugins/installed/optical_drive/plugin.json`

**New tests:**
- `client/src/__tests__/plugin-sandbox/themeHandshake.test.ts`
- `client/src/__tests__/plugin-sandbox/storageBridge.test.ts`
- `client/src/__tests__/plugin-sandbox/storageSdk.test.ts`
- `client/src/__tests__/plugin-sandbox/abiGate.test.ts`
- `backend/tests/plugins/test_plugin_storage_service.py`
- `backend/tests/api/test_plugin_storage_routes.py`
- `client/e2e/plugin-sandbox.spec.ts` (Phase 5)

**New docs (Phase 5):**
- `docs/plugins/PLUGIN_AUTHOR_MIGRATION.md`, `docs/plugins/RUNTIME_ABI.md`

---

## Phase 3a — Runtime UI lib + theme + ABI gate

### Task 1: Theme payload type + host bridge theme/ABI plumbing

**Files:**
- Modify: `client/src/lib/plugin-sandbox/protocol.ts`
- Modify: `client/src/lib/plugin-sandbox/hostBridge.ts`
- Test: `client/src/__tests__/plugin-sandbox/themeHandshake.test.ts`, `client/src/__tests__/plugin-sandbox/abiGate.test.ts`

**Interfaces:**
- Consumes: existing `PluginBridge` (Phase 1), `RpcResult`/`HostPush` (protocol).
- Produces: `ThemePayload { name: string; tokens: Record<string, string> }`; `PluginBridgeOpts` gains `theme: ThemePayload`, `minRuntimeAbi?: number`, `onError?: (code: string) => void`; `PluginBridge.setTheme(theme: ThemePayload): void`. The `init` push payload becomes `{ user, pluginName, theme }`. The `ready` event payload may carry `{ runtime_abi?: number }`.

- [ ] **Step 1: Write the failing tests**

```ts
// client/src/__tests__/plugin-sandbox/themeHandshake.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { PluginBridge } from '../../lib/plugin-sandbox/hostBridge';

vi.mock('../../lib/api', () => ({ apiClient: { request: vi.fn(), post: vi.fn() } }));

function makeIframe() {
  const posted: any[] = [];
  const contentWindow = { postMessage: (m: unknown) => posted.push(m) } as unknown as Window;
  const iframe = { contentWindow } as unknown as HTMLIFrameElement;
  return { iframe, contentWindow, posted };
}
function fireFromFrame(cw: Window, data: unknown) {
  const ev = new MessageEvent('message', { data });
  Object.defineProperty(ev, 'source', { value: cw });
  window.dispatchEvent(ev);
}
const user = { id: 1, username: 'admin', role: 'admin' };
const theme = { name: 'dark', tokens: { '--color-bg-primary': '15, 23, 42' } };

describe('PluginBridge theme handshake', () => {
  beforeEach(() => vi.clearAllMocks());

  it('includes theme in the init push', () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme });
    b.start();
    fireFromFrame(contentWindow, { kind: 'event', name: 'ready', payload: { runtime_abi: 1 } });
    const init = posted.find((m: any) => m.kind === 'push' && m.name === 'init') as any;
    expect(init.payload.theme.tokens['--color-bg-primary']).toBe('15, 23, 42');
    b.dispose();
  });

  it('setTheme posts a theme-changed push', () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme });
    b.start();
    fireFromFrame(contentWindow, { kind: 'event', name: 'ready', payload: { runtime_abi: 1 } });
    b.setTheme({ name: 'ocean', tokens: { '--color-bg-primary': '12, 30, 46' } });
    const changed = posted.find((m: any) => m.kind === 'push' && m.name === 'theme-changed') as any;
    expect(changed.payload.name).toBe('ocean');
    b.dispose();
  });
});
```

```ts
// client/src/__tests__/plugin-sandbox/abiGate.test.ts
import { describe, it, expect, vi } from 'vitest';
import { PluginBridge } from '../../lib/plugin-sandbox/hostBridge';

vi.mock('../../lib/api', () => ({ apiClient: { request: vi.fn(), post: vi.fn() } }));

function makeIframe() {
  const posted: any[] = [];
  const contentWindow = { postMessage: (m: unknown) => posted.push(m) } as unknown as Window;
  const iframe = { contentWindow } as unknown as HTMLIFrameElement;
  return { iframe, contentWindow, posted };
}
function fireFromFrame(cw: Window, data: unknown) {
  const ev = new MessageEvent('message', { data });
  Object.defineProperty(ev, 'source', { value: cw });
  window.dispatchEvent(ev);
}
const user = { id: 1, username: 'admin', role: 'admin' };
const theme = { name: 'dark', tokens: {} };

describe('PluginBridge ABI gate', () => {
  it('refuses init and reports abi_mismatch when runtime is too old', () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const onError = vi.fn();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme, minRuntimeAbi: 2, onError });
    b.start();
    fireFromFrame(contentWindow, { kind: 'event', name: 'ready', payload: { runtime_abi: 1 } });
    expect(onError).toHaveBeenCalledWith('abi_mismatch');
    expect(posted.find((m: any) => m.kind === 'push' && m.name === 'init')).toBeUndefined();
    b.dispose();
  });

  it('sends init when the runtime satisfies min_runtime_abi', () => {
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme, minRuntimeAbi: 1 });
    b.start();
    fireFromFrame(contentWindow, { kind: 'event', name: 'ready', payload: { runtime_abi: 1 } });
    expect(posted.find((m: any) => m.kind === 'push' && m.name === 'init')).toBeTruthy();
    b.dispose();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/themeHandshake.test.ts src/__tests__/plugin-sandbox/abiGate.test.ts`
Expected: FAIL — `theme` not on opts / `setTheme` undefined / no ABI gate.

- [ ] **Step 3: Add the ThemePayload type to protocol.ts**

Append to `client/src/lib/plugin-sandbox/protocol.ts`:

```ts
export interface ThemePayload {
  name: string;
  tokens: Record<string, string>;
}
```

- [ ] **Step 4: Wire theme + ABI into hostBridge.ts**

Edit `client/src/lib/plugin-sandbox/hostBridge.ts`. Add the import and extend opts:

```ts
import { isRpcRequest, isIframeEvent, type RpcResult, type HostPush, type ThemePayload } from './protocol';
```

Extend `PluginBridgeOpts`:

```ts
export interface PluginBridgeOpts {
  iframe: HTMLIFrameElement;
  pluginName: string;
  grantedScopes: string[];
  user: User;
  theme: ThemePayload;
  minRuntimeAbi?: number;
  onResize?: (height: number) => void;
  onNavigate?: (path: string) => void;
  onError?: (code: string) => void;
  timeoutMs?: number;
}
```

Add a mutable theme field + `setTheme`, and replace the `ready` branch with the ABI gate. The class body becomes:

```ts
export class PluginBridge {
  private listener = (ev: MessageEvent) => this.handleMessage(ev);
  private opts: PluginBridgeOpts;
  private theme: ThemePayload;
  private started = false;
  constructor(opts: PluginBridgeOpts) {
    this.opts = opts;
    this.theme = opts.theme;
  }

  start(): void {
    this.started = true;
    window.addEventListener('message', this.listener);
  }
  dispose(): void {
    this.started = false;
    window.removeEventListener('message', this.listener);
  }

  /** Update the active theme; if the frame is live, push it so the plugin restyles. */
  setTheme(theme: ThemePayload): void {
    this.theme = theme;
    if (this.started) {
      this.post({ kind: 'push', name: 'theme-changed', payload: theme });
    }
  }

  private post(msg: RpcResult | HostPush): void {
    this.opts.iframe.contentWindow?.postMessage(msg, '*');
  }

  private async handleMessage(ev: MessageEvent): Promise<void> {
    if (ev.source !== this.opts.iframe.contentWindow) return;
    const data = ev.data;

    if (isIframeEvent(data)) {
      if (data.name === 'ready') {
        const runtimeAbi = (data.payload as { runtime_abi?: unknown })?.runtime_abi;
        const abi = typeof runtimeAbi === 'number' ? runtimeAbi : 1;
        if (this.opts.minRuntimeAbi && abi < this.opts.minRuntimeAbi) {
          this.opts.onError?.('abi_mismatch');
          return;
        }
        this.post({
          kind: 'push', name: 'init',
          payload: { user: this.opts.user, pluginName: this.opts.pluginName, theme: this.theme },
        });
      } else if (data.name === 'resize') {
        const h = (data.payload as { height?: unknown })?.height;
        if (typeof h === 'number') this.opts.onResize?.(h);
      } else if (data.name === 'error') {
        this.opts.onError?.('plugin_error');
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

  // dispatch / apiCall unchanged for now (storage added in Task 7)
```

Keep the existing `dispatch` and `apiCall` methods exactly as they are.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/themeHandshake.test.ts src/__tests__/plugin-sandbox/abiGate.test.ts`
Expected: PASS (4 tests). Re-run the existing `hostBridge.test.ts` to confirm no regression — its `new PluginBridge({...})` calls now need a `theme`:

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/hostBridge.test.ts`
Expected: FAIL (missing `theme` in opts). Fix by adding `theme: { name: 'dark', tokens: {} }` to each `new PluginBridge({...})` in `hostBridge.test.ts`, then re-run → PASS.

- [ ] **Step 6: Commit**

```bash
git add client/src/lib/plugin-sandbox/protocol.ts client/src/lib/plugin-sandbox/hostBridge.ts client/src/__tests__/plugin-sandbox/themeHandshake.test.ts client/src/__tests__/plugin-sandbox/abiGate.test.ts client/src/__tests__/plugin-sandbox/hostBridge.test.ts
git commit -m "feat(plugin-sandbox): theme handshake + ABI gate in host bridge"
```

---

### Task 2: Full `window.BaluHost` surface in the runtime

**Files:**
- Create: `client/src/plugin-runtime/surface.ts`
- Modify: `client/src/plugin-runtime/index.ts`
- Test: covered by the build step (Task 3) + the e2e (Phase 5); add a light unit test of `buildSurface` shape.
- Test: `client/src/__tests__/plugin-sandbox/surface.test.ts`

**Interfaces:**
- Consumes: React, `lucide-react`, `client/src/components/ui`, `client/src/lib/formatters`.
- Produces: `buildSurface(): { React, hooks, ui, icons, utils }` from `surface.ts`. `index.ts` assembles `window.BaluHost = { ...buildSurface(), api, toast, storage, navigate, user }` on `init` and applies theme tokens.

- [ ] **Step 1: Write the failing test**

```ts
// client/src/__tests__/plugin-sandbox/surface.test.ts
import { describe, it, expect } from 'vitest';
import { buildSurface } from '../../plugin-runtime/surface';

describe('buildSurface', () => {
  it('exposes React, the ui primitive set, icons, and utils', () => {
    const s = buildSurface();
    expect(typeof s.React.createElement).toBe('function');
    expect(typeof s.hooks.useState).toBe('function');
    // full primitive set (matches the old initPluginSDK surface)
    for (const k of ['Button','Card','CardHeader','CardContent','CardFooter','Badge','Modal',
      'Input','Textarea','Select','ProgressBar','Spinner','LoadingOverlay','EmptyState',
      'Tabs','TabPanel','ByteSizeInput']) {
      expect(s.ui[k as keyof typeof s.ui], `ui.${k}`).toBeTruthy();
    }
    expect(typeof s.icons).toBe('object');
    expect(typeof s.utils.formatBytes).toBe('function');
    expect(s.utils.cn('a', false, 'b')).toBe('a b');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/surface.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `surface.ts`**

```ts
// client/src/plugin-runtime/surface.ts
// The non-proxy half of window.BaluHost, bundled INTO the runtime and run
// inside the sandbox iframe. Mirrors the old main-context pluginSDK surface
// (minus the tokened api/toast, which are postMessage proxies in index.ts).
import React, {
  useState, useEffect, useCallback, useMemo, useRef,
  useContext, createContext, memo, forwardRef,
} from 'react';
import * as LucideIcons from 'lucide-react';
import {
  Button, Card, CardHeader, CardContent, CardFooter, Badge, Modal, Input,
  Textarea, Select, ProgressBar, Spinner, LoadingOverlay, EmptyState,
  Tabs, TabPanel, ByteSizeInput,
} from '../components/ui';
import { formatBytes as _formatBytes } from '../lib/formatters';

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes === 0) return '0 B';
  return _formatBytes(bytes);
}
function formatDate(date: string | Date, options?: Intl.DateTimeFormatOptions): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleString(undefined, options);
}
function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return '';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}
function formatUptime(seconds: number | null | undefined): string {
  if (!seconds) return '-';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}
function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ');
}

export function buildSurface() {
  return {
    React,
    hooks: { useState, useEffect, useCallback, useMemo, useRef, useContext, createContext, memo, forwardRef },
    ui: {
      Button, Card, CardHeader, CardContent, CardFooter, Badge, Modal, Input,
      Textarea, Select, ProgressBar, Spinner, LoadingOverlay, EmptyState,
      Tabs, TabPanel, ByteSizeInput,
    },
    icons: LucideIcons,
    utils: { formatBytes, formatDate, formatDuration, formatUptime, cn },
  };
}
```

- [ ] **Step 4: Assemble the full SDK + apply theme in `index.ts`**

Replace `client/src/plugin-runtime/index.ts` with:

```ts
// Boots inside the sandbox iframe: wires postMessage, exposes the full
// window.BaluHost (React + ui + icons + utils + proxied api/toast/storage/
// navigate), applies theme tokens, then loads the plugin bundle.
import './runtime.css';
import { createSandboxSdk } from './sdk';
import { buildSurface } from './surface';

const RUNTIME_ABI = 1;

const sdk = createSandboxSdk((msg) => window.parent.postMessage(msg, '*'));

function applyTheme(theme: unknown): void {
  const tokens = (theme as { tokens?: Record<string, string> })?.tokens;
  if (!tokens) return;
  const root = document.documentElement;
  for (const [k, v] of Object.entries(tokens)) root.style.setProperty(k, v);
}

window.addEventListener('message', (ev) => {
  const data = ev.data;
  if (data && data.kind === 'rpc-result') sdk._receive(data);
  if (data && data.kind === 'push' && data.name === 'theme-changed') applyTheme(data.payload);
  if (data && data.kind === 'push' && data.name === 'init') {
    applyTheme((data.payload as { theme?: unknown }).theme);
    (window as unknown as { BaluHost: unknown }).BaluHost = {
      ...buildSurface(),
      api: sdk.api,
      toast: sdk.toast,
      storage: sdk.storage,
      navigate: sdk.navigate,
      user: (data.payload as { user: unknown }).user,
    };
    void loadPluginBundle();
  }
});

async function loadPluginBundle(): Promise<void> {
  const meta = document.querySelector('meta[name="plugin-bundle"]') as HTMLMetaElement | null;
  if (!meta) return;
  await import(/* @vite-ignore */ meta.content);
}

// Announce readiness (with our ABI) so the host responds with `init`.
window.parent.postMessage({ kind: 'event', name: 'ready', payload: { runtime_abi: RUNTIME_ABI } }, '*');
```

(`sdk.storage` and `runtime.css` are created in Tasks 8 and 3; this step will not typecheck until those land — that's fine, the commit happens after Task 3 wires the CSS. To keep this task self-contained and green, temporarily import a stub: add `storage: (sdk as { storage?: unknown }).storage,` is NOT needed — instead, land Task 3 and Task 8 before building. For the unit test in this task, only `surface.ts` is exercised.)

- [ ] **Step 5: Run the surface test**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/surface.test.ts`
Expected: PASS (1 test).

- [ ] **Step 6: Commit**

```bash
git add client/src/plugin-runtime/surface.ts client/src/plugin-runtime/index.ts client/src/__tests__/plugin-sandbox/surface.test.ts
git commit -m "feat(plugin-sandbox): full window.BaluHost surface + theme apply in runtime"
```

---

### Task 3: Compile `plugin-runtime.css` + link it from host.html

**Files:**
- Create: `client/src/plugin-runtime/runtime.css`
- Modify: `client/vite.runtime.config.ts`
- Modify: `backend/app/api/routes/plugins.py` (host.html `<head>`)
- Test: `backend/tests/api/test_plugin_sandbox_assets.py` (extend)

**Interfaces:**
- Produces: `client/public/plugin-runtime.css` build output; `host.html` `<head>` gains `<link rel="stylesheet" href="/plugin-runtime.css">`.

- [ ] **Step 1: Write the failing backend assertion**

Add to `backend/tests/api/test_plugin_sandbox_assets.py`:

```python
def test_host_html_links_runtime_css(client):
    resp = client.get("/api/plugins/storage_analytics/ui/host.html")
    if resp.status_code == 200:
        assert '/plugin-runtime.css' in resp.text
        assert 'rel="stylesheet"' in resp.text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_plugin_sandbox_assets.py::test_host_html_links_runtime_css -v`
Expected: FAIL — no stylesheet link.

- [ ] **Step 3: Create `runtime.css`**

```css
/* client/src/plugin-runtime/runtime.css
   Compiled standalone into client/public/plugin-runtime.css and loaded by the
   sandbox host.html. Carries the Tailwind utilities the bundled ui/ primitives
   use; theme CSS variables are injected at runtime via the init handshake. */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 4: Make the runtime build emit a fixed-name CSS asset**

Edit `client/vite.runtime.config.ts` so the CSS asset is named `plugin-runtime.css`:

```ts
import { defineConfig } from 'vite';

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
    rollupOptions: {
      output: {
        entryFileNames: 'plugin-runtime.js',
        assetFileNames: (info) =>
          info.name && info.name.endsWith('.css') ? 'plugin-runtime.css' : '[name][extname]',
      },
    },
  },
});
```

- [ ] **Step 5: Add the `<link>` to the generated host.html**

In `backend/app/api/routes/plugins.py`, in the `host.html` branch, add the stylesheet link to `<head>`:

```python
        html_doc = (
            '<!doctype html><html><head><meta charset="utf-8">'
            '<link rel="stylesheet" href="/plugin-runtime.css">'
            f'<meta name="plugin-bundle" content="/api/plugins/{safe_name}/ui/{safe_bundle_path}">'
            '</head><body><div id="plugin-root"></div>'
            '<script src="/plugin-runtime.js"></script></body></html>'
        )
```

- [ ] **Step 6: Build the runtime and verify both assets emit**

Run: `cd client && npm run build:runtime`
Expected: emits `client/public/plugin-runtime.js` AND `client/public/plugin-runtime.css`, no errors.

- [ ] **Step 7: Run the backend test**

Run: `cd backend && python -m pytest tests/api/test_plugin_sandbox_assets.py -v`
Expected: PASS (all, incl. the new link assertion).

- [ ] **Step 8: Confirm `.gitignore` covers the CSS**

Ensure `client/.gitignore` contains both `public/plugin-runtime.js` and `public/plugin-runtime.css` (add the css line if missing).

- [ ] **Step 9: Build the full client to confirm `index.ts` typechecks**

Run: `cd client && npm run build`
Expected: green. (If `sdk.storage` is not yet present, this fails — land Task 8 first, or temporarily comment the `storage:` line and restore in Task 8. Note which you did in the commit message.)

- [ ] **Step 10: Commit**

```bash
git add client/src/plugin-runtime/runtime.css client/vite.runtime.config.ts client/.gitignore backend/app/api/routes/plugins.py backend/tests/api/test_plugin_sandbox_assets.py
git commit -m "feat(plugin-sandbox): compile plugin-runtime.css + link from host.html"
```

---

### Task 4: PluginSandboxHost feeds theme + ABI; PluginPage passes min_runtime_abi

**Files:**
- Modify: `client/src/components/plugins/PluginSandboxHost.tsx`
- Modify: `client/src/components/PluginPage.tsx`
- Test: `client/src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx` (extend)

**Interfaces:**
- Consumes: `PluginBridge` (Task 1), `useTheme` + `themes` from `client/src/contexts/ThemeContext`.
- Produces: `<PluginSandboxHost pluginName user grantedScopes minRuntimeAbi? />`; pushes `theme-changed` on host theme switch; renders an error state on `onError`.

- [ ] **Step 1: Write/extend the failing test**

Add to `client/src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx`:

```tsx
import { ThemeProvider } from '../../contexts/ThemeContext';

it('still renders the opaque-origin iframe with a ThemeProvider present', () => {
  const user = { id: 1, username: 'admin', role: 'admin' };
  const { container } = render(
    <ThemeProvider>
      <PluginSandboxHost pluginName="weather" user={user} grantedScopes={[]} />
    </ThemeProvider>
  );
  const iframe = container.querySelector('iframe')!;
  expect(iframe.getAttribute('sandbox')).toBe('allow-scripts');
});
```

(The existing two tests render without a provider — keep them; `useTheme` has a built-in fallback when no provider is present, so they stay green.)

- [ ] **Step 2: Run it to verify current state**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx`
Expected: the new test FAILS to compile/run until `react-router` `useNavigate` is satisfied — it already is via the existing tests' setup; if the existing tests wrap in a router, wrap the new one the same way. Match the existing test's render harness exactly.

- [ ] **Step 3: Update `PluginSandboxHost.tsx`**

```tsx
// client/src/components/plugins/PluginSandboxHost.tsx
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PluginBridge } from '../../lib/plugin-sandbox/hostBridge';
import { useTheme, themes } from '../../contexts/ThemeContext';

interface User { id: number; username: string; role: string }

interface Props {
  pluginName: string;
  user: User;
  grantedScopes: string[];
  minRuntimeAbi?: number;
}

export default function PluginSandboxHost({ pluginName, user, grantedScopes, minRuntimeAbi }: Props) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const bridgeRef = useRef<PluginBridge | null>(null);
  const navigate = useNavigate();
  const { theme } = useTheme();
  const [height, setHeight] = useState(480);
  const [error, setError] = useState<string | null>(null);

  const scopesKey = grantedScopes.join(',');
  const userId = user.id;

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    setError(null);
    const bridge = new PluginBridge({
      iframe,
      pluginName,
      grantedScopes,
      user,
      minRuntimeAbi,
      theme: { name: theme, tokens: themes[theme].colors },
      onResize: (h) => setHeight(Math.max(120, Math.ceil(h))),
      onNavigate: (path) => navigate(path),
      onError: (code) => setError(code),
    });
    bridge.start();
    bridgeRef.current = bridge;
    return () => { bridge.dispose(); bridgeRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pluginName, scopesKey, userId, minRuntimeAbi, navigate]);

  // Push theme changes WITHOUT recreating the bridge (which would reload the iframe).
  useEffect(() => {
    bridgeRef.current?.setTheme({ name: theme, tokens: themes[theme].colors });
  }, [theme]);

  if (error === 'abi_mismatch') {
    return (
      <div className="p-6 rounded-lg border border-amber-500/40 bg-amber-500/10 text-amber-200 text-sm">
        This plugin needs a newer BaluHost runtime.
      </div>
    );
  }

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

- [ ] **Step 4: Pass `min_runtime_abi` from PluginPage**

In `client/src/components/PluginPage.tsx`, update the render to forward the ABI floor:

```tsx
      <PluginSandboxHost
        pluginName={pluginName!}
        user={user}
        grantedScopes={pluginInfo?.granted_api_scopes ?? []}
        minRuntimeAbi={pluginInfo?.min_runtime_abi}
      />
```

(`min_runtime_abi` is added to the plugin-info type/route in Task 9b below; until then TypeScript may flag it — land Task 9b's frontend type change in the same commit, or use `(pluginInfo as { min_runtime_abi?: number })?.min_runtime_abi`.)

- [ ] **Step 5: Run the sandbox suite + typecheck**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/ && npx tsc --noEmit`
Expected: all sandbox tests PASS; no type errors.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/plugins/PluginSandboxHost.tsx client/src/components/PluginPage.tsx client/src/__tests__/plugin-sandbox/PluginSandboxHost.test.tsx
git commit -m "feat(plugin-sandbox): feed theme + ABI floor into the sandbox host"
```

---

## Phase 3b — Storage channel + backend

### Task 5: `plugin_storage` model + migration

**Files:**
- Create: `backend/app/models/plugin_storage.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_plugin_storage.py`
- Test: `backend/tests/plugins/test_plugin_storage_service.py` (model round-trip part)

**Interfaces:**
- Produces: `PluginStorage(plugin_name: str, user_id: int, key: str, value: Any, updated_at)`, unique `(plugin_name, user_id, key)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/plugins/test_plugin_storage_service.py
from app.models.plugin_storage import PluginStorage


def test_plugin_storage_roundtrip(db_session):
    row = PluginStorage(plugin_name="weather", user_id=1, key="units", value={"temp": "C"})
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    assert row.value == {"temp": "C"}
    assert row.plugin_name == "weather"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_storage_service.py::test_plugin_storage_roundtrip -v`
Expected: FAIL — module `app.models.plugin_storage` not found.

- [ ] **Step 3: Create the model**

```python
# backend/app/models/plugin_storage.py
"""Per-(plugin, user) key-value storage for sandboxed plugin UIs."""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, Integer, JSON, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class PluginStorage(Base):
    """A single key-value entry owned by (plugin_name, user_id)."""

    __tablename__ = "plugin_storage"
    __table_args__ = (
        UniqueConstraint("plugin_name", "user_id", "key", name="uq_plugin_storage_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plugin_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 4: Register in `models/__init__.py`**

Add the import and `__all__` entry alongside the other plugin model:

```python
from app.models.plugin_storage import PluginStorage  # noqa: F401
```
(and add `"PluginStorage"` to `__all__` if that list is maintained explicitly.)

- [ ] **Step 5: Run the round-trip test**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_storage_service.py::test_plugin_storage_roundtrip -v`
Expected: PASS (the test DB is built from models).

- [ ] **Step 6: Generate the migration against the real head**

```bash
cd backend
alembic heads
alembic revision --autogenerate -m "plugin_storage table"
```

Verify the new file's `down_revision` equals the `alembic heads` output. The `upgrade()` must `op.create_table('plugin_storage', …)` with the unique constraint; `downgrade()` drops it. If autogenerate misses the constraint, add it explicitly.

- [ ] **Step 7: Apply + verify**

Run: `cd backend && alembic upgrade head && alembic current`
Expected: applies cleanly; `alembic current` shows the new head.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/plugin_storage.py backend/app/models/__init__.py backend/alembic/versions/*plugin_storage*.py backend/tests/plugins/test_plugin_storage_service.py
git commit -m "feat(plugin-sandbox): plugin_storage model + migration"
```

---

### Task 6: Storage service (quota-checked CRUD) + routes

**Files:**
- Create: `backend/app/services/plugin_storage_service.py`
- Modify: `backend/app/schemas/plugin.py` (add `PluginStorageSetRequest`)
- Modify: `backend/app/api/routes/plugins.py` (add `_storage` routes)
- Test: `backend/tests/plugins/test_plugin_storage_service.py` (quota/isolation), `backend/tests/api/test_plugin_storage_routes.py`

**Interfaces:**
- Consumes: `PluginStorage` (Task 5).
- Produces: service `get_value/list_keys/set_value/delete_value`, `StorageQuotaError(code='storage_quota')`, `MAX_VALUE_BYTES=65536`, `MAX_KEYS=100`; routes `GET/PUT/DELETE /api/plugins/{name}/_storage/{key}` + `GET /api/plugins/{name}/_storage`.

- [ ] **Step 1: Write the failing service tests**

Append to `backend/tests/plugins/test_plugin_storage_service.py`:

```python
import pytest
from app.services import plugin_storage_service as svc


def test_set_get_delete(db_session):
    svc.set_value(db_session, "weather", 1, "units", {"t": "C"})
    found, value = svc.get_value(db_session, "weather", 1, "units")
    assert found and value == {"t": "C"}
    assert svc.list_keys(db_session, "weather", 1) == ["units"]
    assert svc.delete_value(db_session, "weather", 1, "units") is True
    found, _ = svc.get_value(db_session, "weather", 1, "units")
    assert found is False


def test_per_user_isolation(db_session):
    svc.set_value(db_session, "weather", 1, "k", "A")
    svc.set_value(db_session, "weather", 2, "k", "B")
    _, v1 = svc.get_value(db_session, "weather", 1, "k")
    _, v2 = svc.get_value(db_session, "weather", 2, "k")
    assert v1 == "A" and v2 == "B"
    assert svc.list_keys(db_session, "weather", 1) == ["k"]


def test_value_size_quota(db_session):
    big = "x" * (svc.MAX_VALUE_BYTES + 1)
    with pytest.raises(svc.StorageQuotaError):
        svc.set_value(db_session, "weather", 1, "k", big)


def test_key_count_quota(db_session):
    for i in range(svc.MAX_KEYS):
        svc.set_value(db_session, "weather", 1, f"k{i}", i)
    with pytest.raises(svc.StorageQuotaError):
        svc.set_value(db_session, "weather", 1, "overflow", 1)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_storage_service.py -v`
Expected: FAIL — service module missing.

- [ ] **Step 3: Write the service**

```python
# backend/app/services/plugin_storage_service.py
"""Quota-checked, per-(plugin, user) key-value store for plugin UIs."""
import json
from typing import Any, Tuple

from sqlalchemy.orm import Session

from app.models.plugin_storage import PluginStorage

MAX_VALUE_BYTES = 64 * 1024
MAX_KEYS = 100


class StorageQuotaError(Exception):
    """Raised when a write would exceed the per-(plugin, user) quota."""
    code = "storage_quota"


def get_value(db: Session, plugin_name: str, user_id: int, key: str) -> Tuple[bool, Any]:
    row = (
        db.query(PluginStorage)
        .filter_by(plugin_name=plugin_name, user_id=user_id, key=key)
        .one_or_none()
    )
    return (True, row.value) if row is not None else (False, None)


def list_keys(db: Session, plugin_name: str, user_id: int) -> list[str]:
    rows = (
        db.query(PluginStorage.key)
        .filter_by(plugin_name=plugin_name, user_id=user_id)
        .order_by(PluginStorage.key)
        .all()
    )
    return [r[0] for r in rows]


def set_value(db: Session, plugin_name: str, user_id: int, key: str, value: Any) -> None:
    serialized = json.dumps(value)
    if len(serialized.encode("utf-8")) > MAX_VALUE_BYTES:
        raise StorageQuotaError(f"value exceeds {MAX_VALUE_BYTES} bytes")

    row = (
        db.query(PluginStorage)
        .filter_by(plugin_name=plugin_name, user_id=user_id, key=key)
        .one_or_none()
    )
    if row is None:
        count = (
            db.query(PluginStorage)
            .filter_by(plugin_name=plugin_name, user_id=user_id)
            .count()
        )
        if count >= MAX_KEYS:
            raise StorageQuotaError(f"key limit {MAX_KEYS} reached")
        row = PluginStorage(plugin_name=plugin_name, user_id=user_id, key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()


def delete_value(db: Session, plugin_name: str, user_id: int, key: str) -> bool:
    row = (
        db.query(PluginStorage)
        .filter_by(plugin_name=plugin_name, user_id=user_id, key=key)
        .one_or_none()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
```

- [ ] **Step 4: Run the service tests**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_storage_service.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Add the request schema**

In `backend/app/schemas/plugin.py`, add:

```python
class PluginStorageSetRequest(BaseModel):
    value: Any
```

(Ensure `Any` is imported: `from typing import Any`, and `BaseModel` is already imported in this module.)

- [ ] **Step 6: Write the failing route test**

```python
# backend/tests/api/test_plugin_storage_routes.py
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_storage_put_get_delete_roundtrip(client, user_auth_headers):
    base = "/api/plugins/storage_analytics/_storage"
    put = client.put(f"{base}/units", headers=user_auth_headers, json={"value": {"t": "C"}})
    assert put.status_code in (200, 204)
    got = client.get(f"{base}/units", headers=user_auth_headers)
    assert got.status_code == 200 and got.json()["value"] == {"t": "C"}
    keys = client.get(base, headers=user_auth_headers)
    assert "units" in keys.json()["keys"]
    dele = client.delete(f"{base}/units", headers=user_auth_headers)
    assert dele.status_code == 204
    missing = client.get(f"{base}/units", headers=user_auth_headers)
    assert missing.status_code == 404


def test_storage_requires_auth(client):
    resp = client.get("/api/plugins/storage_analytics/_storage/units")
    assert resp.status_code in (401, 403)
```

(Use the project's existing authenticated-user fixture; match its real name — replace `user_auth_headers` with whatever `backend/tests/conftest.py` provides. If only an admin fixture exists, use it.)

- [ ] **Step 7: Run it to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_plugin_storage_routes.py -v`
Expected: FAIL — routes return 404 (not registered).

- [ ] **Step 8: Add the routes**

In `backend/app/api/routes/plugins.py`, near the `_audit/scope-denied` route (so they sit before the `ui/{file_path:path}` catch-all), add imports + the four routes:

```python
from app.services import plugin_storage_service
from app.schemas.plugin import PluginStorageSetRequest  # add to the existing schema import block


@router.get("/{name}/_storage")
@user_limiter.limit(get_limit("admin_operations"))
async def storage_list_keys(
    request: Request, response: Response, name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List this user's storage keys for the plugin."""
    return {"keys": plugin_storage_service.list_keys(db, name, current_user.id)}


@router.get("/{name}/_storage/{key}")
@user_limiter.limit(get_limit("admin_operations"))
async def storage_get(
    request: Request, response: Response, name: str, key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    found, value = plugin_storage_service.get_value(db, name, current_user.id, key)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    return {"value": value}


@router.put("/{name}/_storage/{key}")
@user_limiter.limit(get_limit("admin_operations"))
async def storage_set(
    request: Request, response: Response, name: str, key: str,
    body: PluginStorageSetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        plugin_storage_service.set_value(db, name, current_user.id, key, body.value)
    except plugin_storage_service.StorageQuotaError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    return {"ok": True}


@router.delete("/{name}/_storage/{key}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("admin_operations"))
async def storage_delete(
    request: Request, response: Response, name: str, key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    plugin_storage_service.delete_value(db, name, current_user.id, key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 9: Run the route tests**

Run: `cd backend && python -m pytest tests/api/test_plugin_storage_routes.py -v`
Expected: PASS (2 tests).

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/plugin_storage_service.py backend/app/schemas/plugin.py backend/app/api/routes/plugins.py backend/tests/plugins/test_plugin_storage_service.py backend/tests/api/test_plugin_storage_routes.py
git commit -m "feat(plugin-sandbox): per-user plugin_storage service + _storage routes"
```

---

### Task 7: Host bridge `storage` dispatch

**Files:**
- Modify: `client/src/lib/plugin-sandbox/hostBridge.ts`
- Test: `client/src/__tests__/plugin-sandbox/storageBridge.test.ts`

**Interfaces:**
- Consumes: `apiClient` (`get/put/delete`), service routes from Task 6.
- Produces: `dispatch` handles `channel === 'storage'` with methods `get/set/del/keys`, mapping to the `_storage` routes; 404 on `get` resolves to `undefined`; 413 rejects `{ code: 'storage_quota' }`.

- [ ] **Step 1: Write the failing test**

```ts
// client/src/__tests__/plugin-sandbox/storageBridge.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PluginBridge } from '../../lib/plugin-sandbox/hostBridge';

vi.mock('../../lib/api', () => ({
  apiClient: { request: vi.fn(), post: vi.fn(), get: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));
import { apiClient } from '../../lib/api';

function makeIframe() {
  const posted: any[] = [];
  const contentWindow = { postMessage: (m: unknown) => posted.push(m) } as unknown as Window;
  const iframe = { contentWindow } as unknown as HTMLIFrameElement;
  return { iframe, contentWindow, posted };
}
function fireFromFrame(cw: Window, data: unknown) {
  const ev = new MessageEvent('message', { data });
  Object.defineProperty(ev, 'source', { value: cw });
  window.dispatchEvent(ev);
}
const user = { id: 1, username: 'admin', role: 'admin' };
const theme = { name: 'dark', tokens: {} };

describe('PluginBridge storage channel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('storage.set maps to PUT and resolves', async () => {
    (apiClient.put as any).mockResolvedValue({ data: { ok: true } });
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme });
    b.start();
    fireFromFrame(contentWindow, { kind: 'rpc', id: 's1', channel: 'storage', method: 'set', args: ['k', { a: 1 }] });
    await vi.waitFor(() => expect(posted.find((m: any) => m.id === 's1')).toBeTruthy());
    expect(apiClient.put).toHaveBeenCalledWith('/api/plugins/weather/_storage/k', { value: { a: 1 } });
    const res = posted.find((m: any) => m.id === 's1') as any;
    expect(res.ok).toBe(true);
    b.dispose();
  });

  it('storage.get returns the unwrapped value', async () => {
    (apiClient.get as any).mockResolvedValue({ data: { value: 42 } });
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme });
    b.start();
    fireFromFrame(contentWindow, { kind: 'rpc', id: 's2', channel: 'storage', method: 'get', args: ['k'] });
    await vi.waitFor(() => expect(posted.find((m: any) => m.id === 's2')).toBeTruthy());
    const res = posted.find((m: any) => m.id === 's2') as any;
    expect(res.ok).toBe(true);
    expect(res.value).toBe(42);
    b.dispose();
  });

  it('storage.get resolves undefined on 404', async () => {
    (apiClient.get as any).mockRejectedValue({ response: { status: 404 } });
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme });
    b.start();
    fireFromFrame(contentWindow, { kind: 'rpc', id: 's3', channel: 'storage', method: 'get', args: ['missing'] });
    await vi.waitFor(() => expect(posted.find((m: any) => m.id === 's3')).toBeTruthy());
    const res = posted.find((m: any) => m.id === 's3') as any;
    expect(res.ok).toBe(true);
    expect(res.value).toBeUndefined();
    b.dispose();
  });

  it('storage.set rejects storage_quota on 413', async () => {
    (apiClient.put as any).mockRejectedValue({ response: { status: 413, data: { detail: 'too big' } } });
    const { iframe, contentWindow, posted } = makeIframe();
    const b = new PluginBridge({ iframe, pluginName: 'weather', grantedScopes: [], user, theme });
    b.start();
    fireFromFrame(contentWindow, { kind: 'rpc', id: 's4', channel: 'storage', method: 'set', args: ['k', 'x'] });
    await vi.waitFor(() => expect(posted.find((m: any) => m.id === 's4')).toBeTruthy());
    const res = posted.find((m: any) => m.id === 's4') as any;
    expect(res.ok).toBe(false);
    expect(res.error.code).toBe('storage_quota');
    b.dispose();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/storageBridge.test.ts`
Expected: FAIL — storage channel throws `unknown_channel`.

- [ ] **Step 3: Add the storage dispatch**

In `client/src/lib/plugin-sandbox/hostBridge.ts`, extend `dispatch` and add `storageCall`:

```ts
  private async dispatch(channel: string, method: string, args: unknown[]): Promise<unknown> {
    if (channel === 'api') return this.apiCall(method, args);
    if (channel === 'storage') return this.storageCall(method, args);
    if (channel === 'navigate') {
      const path = String(args[0] ?? '');
      const prefix = `/plugins/${this.opts.pluginName}`;
      if (path !== prefix && !path.startsWith(prefix + '/')) throw { code: 'navigate_denied', message: 'Out-of-plugin navigation blocked' };
      this.opts.onNavigate?.(path);
      return null;
    }
    throw { code: 'unknown_channel', message: `Unknown channel ${channel}` };
  }

  private async storageCall(method: string, args: unknown[]): Promise<unknown> {
    const base = `/api/plugins/${this.opts.pluginName}/_storage`;
    const key = encodeURIComponent(String(args[0] ?? ''));
    try {
      if (method === 'get') {
        const res = await apiClient.get(`${base}/${key}`);
        return (res.data as { value?: unknown })?.value;
      }
      if (method === 'set') {
        await apiClient.put(`${base}/${key}`, { value: args[1] });
        return { ok: true };
      }
      if (method === 'del') {
        await apiClient.delete(`${base}/${key}`);
        return null;
      }
      if (method === 'keys') {
        const res = await apiClient.get(base);
        return (res.data as { keys?: unknown })?.keys ?? [];
      }
      throw { code: 'unknown_method', message: `Unknown storage method ${method}` };
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (method === 'get' && status === 404) return undefined;
      if (status === 413) throw { code: 'storage_quota', message: 'Plugin storage quota exceeded' };
      throw err;
    }
  }
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/storageBridge.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/lib/plugin-sandbox/hostBridge.ts client/src/__tests__/plugin-sandbox/storageBridge.test.ts
git commit -m "feat(plugin-sandbox): host bridge storage channel (per-user, quota-aware)"
```

---

### Task 8: Runtime SDK `storage` proxy

**Files:**
- Modify: `client/src/plugin-runtime/sdk.ts`
- Test: `client/src/__tests__/plugin-sandbox/storageSdk.test.ts`

**Interfaces:**
- Produces: `createSandboxSdk(...)` return value gains `storage: { get, set, del, keys }`, each a `postMessage` RPC on the `storage` channel.

- [ ] **Step 1: Write the failing test**

```ts
// client/src/__tests__/plugin-sandbox/storageSdk.test.ts
import { describe, it, expect } from 'vitest';
import { createSandboxSdk } from '../../plugin-runtime/sdk';

describe('createSandboxSdk storage', () => {
  it('storage.set posts a storage rpc and resolves on result', async () => {
    const posted: any[] = [];
    const sdk = createSandboxSdk((m) => posted.push(m));
    const p = sdk.storage.set('units', { t: 'C' });
    const req = posted.find((m) => m.kind === 'rpc' && m.channel === 'storage');
    expect(req.method).toBe('set');
    expect(req.args).toEqual(['units', { t: 'C' }]);
    sdk._receive({ kind: 'rpc-result', id: req.id, ok: true, value: { ok: true } });
    await expect(p).resolves.toEqual({ ok: true });
  });

  it('storage.get resolves the value', async () => {
    const posted: any[] = [];
    const sdk = createSandboxSdk((m) => posted.push(m));
    const p = sdk.storage.get('units');
    const req = posted.find((m) => m.kind === 'rpc' && m.channel === 'storage');
    expect(req.method).toBe('get');
    sdk._receive({ kind: 'rpc-result', id: req.id, ok: true, value: { t: 'C' } });
    await expect(p).resolves.toEqual({ t: 'C' });
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/storageSdk.test.ts`
Expected: FAIL — `sdk.storage` is undefined.

- [ ] **Step 3: Add the storage proxy**

In `client/src/plugin-runtime/sdk.ts`, add before the `return`:

```ts
  const storage = {
    get: (key: string) => call('storage', 'get', [key]),
    set: (key: string, value: unknown) => call('storage', 'set', [key, value]),
    del: (key: string) => call('storage', 'del', [key]),
    keys: () => call('storage', 'keys', []),
  };
```

and update the return to include it:

```ts
  return { api, toast, navigate, storage, _receive };
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/storageSdk.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Build the runtime + full client (now that `sdk.storage` exists)**

Run: `cd client && npm run build:runtime && npm run build`
Expected: green; `index.ts`'s `storage: sdk.storage` now typechecks. If Task 3 Step 9 temporarily commented the `storage:` line, restore it now.

- [ ] **Step 6: Commit**

```bash
git add client/src/plugin-runtime/sdk.ts client/src/plugin-runtime/index.ts client/src/__tests__/plugin-sandbox/storageSdk.test.ts
git commit -m "feat(plugin-sandbox): runtime storage proxy; wire into window.BaluHost"
```

---

## Phase 4 — Migrate the UI plugins + remove legacy

### Task 9: Surface `min_runtime_abi` to the SPA + migrate `storage_analytics`

**Files (9a — backend/frontend ABI exposure):**
- Modify: `backend/app/schemas/plugin.py` (the UI-manifest info model)
- Modify: `backend/app/api/routes/plugins.py` (UI-manifest route fills `min_runtime_abi`)
- Modify: `client/src/api/plugins.ts` (the plugin-info type)
- Test: `backend/tests/api/test_plugin_ui_manifest_scopes.py` (extend)

**Files (9b — migrate the plugin):**
- Modify: `backend/app/plugins/installed/storage_analytics/ui/bundle.js`
- Modify: `backend/app/plugins/installed/storage_analytics/plugin.json`

**Interfaces:**
- Produces: the UI-manifest plugin entry carries `min_runtime_abi: int | None`; `client/src/api/plugins.ts`'s plugin type carries `min_runtime_abi?: number`; `storage_analytics` UI consumes `window.BaluHost` (React + api), declares `api_scopes` + `min_runtime_abi`.

- [ ] **Step 1: Write the failing backend test**

Extend `backend/tests/api/test_plugin_ui_manifest_scopes.py` (the existing file that checks `granted_api_scopes`):

```python
def test_ui_manifest_includes_min_runtime_abi(client, admin_auth_headers):
    resp = client.get("/api/plugins/ui/manifest", headers=admin_auth_headers)
    assert resp.status_code == 200
    for entry in resp.json().get("plugins", []):
        assert "min_runtime_abi" in entry
```

(Match the real manifest path + admin fixture used by the existing tests in this file.)

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_plugin_ui_manifest_scopes.py::test_ui_manifest_includes_min_runtime_abi -v`
Expected: FAIL — key absent.

- [ ] **Step 3: Add `min_runtime_abi` to the UI-manifest info model + route**

In `backend/app/schemas/plugin.py`, add to the UI-info model that already carries `granted_api_scopes` (e.g. `PluginUIInfo`):

```python
    min_runtime_abi: Optional[int] = None
```

In `backend/app/api/routes/plugins.py`, where that model is built for the UI manifest, populate it from the loaded manifest (mirroring how `granted_api_scopes` is filled):

```python
        min_runtime_abi=getattr(manifest, "min_runtime_abi", None),
```

(Use the same `manifest` object already loaded in that route; if the route doesn't load the manifest, load it via `load_manifest(plugin_manager.plugins_dir / name)` in a `try/except` like the host.html branch.)

- [ ] **Step 4: Mirror the field in the frontend type**

In `client/src/api/plugins.ts`, add to the plugin-info interface that already has `granted_api_scopes`:

```ts
  min_runtime_abi?: number;
```

- [ ] **Step 5: Run the backend test + frontend typecheck**

Run: `cd backend && python -m pytest tests/api/test_plugin_ui_manifest_scopes.py -v`
Expected: PASS.
Run: `cd client && npx tsc --noEmit`
Expected: clean (PluginPage's `pluginInfo?.min_runtime_abi` now resolves; drop the `as` cast from Task 4 Step 4 if used).

- [ ] **Step 6: Migrate `storage_analytics/ui/bundle.js`**

Replace the top of `backend/app/plugins/installed/storage_analytics/ui/bundle.js` so it consumes the sandbox `window.BaluHost` instead of `window.React` + raw `fetch`. Change the preamble from:

```js
const React = window.React;
const { useState, useEffect } = React;
// API helper
async function fetchPlugin... (raw fetch)
```

to:

```js
// Storage Analytics — sandbox runtime (window.BaluHost externals)
const { React, api, ui, utils } = window.BaluHost;
const { useState, useEffect } = React;
```

Then replace every raw `fetch('/api/...')` / `fetchPlugin(...)` call in the file with the awaited `api.get(...)` / `api.post(...)` equivalent (same URLs, but via `BaluHost.api`, which carries the token through the bridge). Keep the component's JSX/logic otherwise unchanged, and keep its default export shape (the bundle must still expose the component the runtime renders — match how `optical_drive/ui/bundle.js` exposes its `PLUGIN`/default).

- [ ] **Step 7: Declare scopes + ABI in `storage_analytics/plugin.json`**

Add the two fields (storage analytics reads storage info → grant `read:storage`):

```json
  "api_scopes": ["read:storage"],
  "min_runtime_abi": 1,
```

(Insert before the closing `}`; keep valid JSON — add a comma after the preceding `"ui": {...}` line.)

- [ ] **Step 8: Verify backend still loads the manifest**

Run: `cd backend && python -m pytest tests/plugins/test_manifest_api_scopes.py tests/api/test_plugin_ui_manifest_scopes.py -v`
Expected: PASS (manifest parses the new fields).

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas/plugin.py backend/app/api/routes/plugins.py client/src/api/plugins.ts client/src/components/PluginPage.tsx backend/app/plugins/installed/storage_analytics/ui/bundle.js backend/app/plugins/installed/storage_analytics/plugin.json backend/tests/api/test_plugin_ui_manifest_scopes.py
git commit -m "feat(plugin-sandbox): expose min_runtime_abi; migrate storage_analytics to BaluHost.api"
```

---

### Task 10: Migrate `optical_drive` manifest + verify its API calls

**Files:**
- Modify: `backend/app/plugins/installed/optical_drive/plugin.json`
- Inspect: `backend/app/plugins/installed/optical_drive/ui/bundle.js` (no rewrite expected — it already uses `window.BaluHost`)

**Interfaces:**
- Produces: `optical_drive/plugin.json` declares `api_scopes` + `min_runtime_abi: 1`; all of its `api.*` calls are own-routes or covered by a granted scope.

- [ ] **Step 1: Audit the bundle's API calls**

Read `backend/app/plugins/installed/optical_drive/ui/bundle.js` and list every `api.get/post/put/delete(...)` URL. Each must be either `/api/plugins/optical_drive/...` (own-route, always allowed) or a Core route covered by a scope in `client/src/lib/plugin-sandbox/scopeCatalog.ts`. Note any Core call that is NOT covered.

- [ ] **Step 2: Decide scopes**

If every call is an own-route, `api_scopes` is `[]`. If a Core call needs a scope already in the catalog (`read:system-info`, `read:storage`, `read:power`), add that scope. If a Core call has no catalog entry, prefer re-pointing it onto an own `/api/plugins/optical_drive/...` route (the plugin's backend already serves its own routes) — do NOT widen the Core catalog in this task.

- [ ] **Step 3: Update `optical_drive/plugin.json`**

Add (example assuming all own-routes):

```json
  "api_scopes": [],
  "min_runtime_abi": 1,
```

- [ ] **Step 4: Verify manifest parses**

Run: `cd backend && python -m pytest tests/plugins/test_manifest_api_scopes.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/installed/optical_drive/plugin.json
git commit -m "feat(plugin-sandbox): declare optical_drive api_scopes + min_runtime_abi"
```

---

### Task 11: Remove the legacy main-context SDK (close the audit gap)

**Files:**
- Delete: `client/src/lib/pluginLoader.ts`, `client/src/lib/pluginSDK.ts`
- Modify: `client/src/main.tsx`
- Test: build + a grep assertion

**Interfaces:**
- Produces: `window.BaluHost` no longer exists in the host browsing context; no references to `pluginLoader`/`pluginSDK`/`initPluginSDK` remain in `client/src`.

- [ ] **Step 1: Confirm there are no other importers**

Run (PowerShell-safe; lists any remaining references):

```bash
cd client && npx tsc --noEmit && node -e "const cp=require('child_process');const out=cp.execSync('git grep -n -E \"pluginLoader|pluginSDK|initPluginSDK|window.BaluHost\" -- src || true').toString();console.log(out||'(none)')"
```

Expected before edits: references in `main.tsx` (and the two files themselves). PluginPage already uses the sandbox host (no loader import).

- [ ] **Step 2: Remove the SDK boot from `main.tsx`**

Edit `client/src/main.tsx`: delete the import line `import { initPluginSDK } from './lib/pluginSDK'` and the `initPluginSDK();` call (with its comment). The file's top becomes:

```tsx
import { StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { Toaster } from 'react-hot-toast'
import { ThemeProvider } from './contexts/ThemeContext'
import './i18n' // Initialize i18n before app renders
import './index.css'
import App from './App.tsx'
```

and the `createRoot(...)` block follows directly (no `initPluginSDK()` line).

- [ ] **Step 3: Delete the legacy files**

```bash
cd client && git rm src/lib/pluginLoader.ts src/lib/pluginSDK.ts
```

- [ ] **Step 4: Verify nothing references them + typecheck + build**

Run:

```bash
cd client && node -e "const cp=require('child_process');const out=cp.execSync('git grep -n -E \"pluginLoader|pluginSDK|initPluginSDK|window\\.BaluHost\" -- src || true').toString();if(out.trim()){console.error('LEAK:\n'+out);process.exit(1)}else{console.log('clean')}"
npx tsc --noEmit && npm run build
```

Expected: `clean`, no type errors, build green. If `tsc` flags the now-removed `Window.BaluHost`/`BaluHostPlugins` ambient types being referenced anywhere, remove those references too.

- [ ] **Step 5: Run the full sandbox suite**

Run: `cd client && npx vitest run src/__tests__/plugin-sandbox/`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add client/src/main.tsx client/src/lib/pluginLoader.ts client/src/lib/pluginSDK.ts
git commit -m "feat(plugin-sandbox): remove main-context pluginSDK/pluginLoader (close audit gap)"
```

---

## Phase 5 — E2E + docs

### Task 12: Playwright sandbox E2E

**Files:**
- Create: `client/e2e/plugin-sandbox.spec.ts`
- Inspect: the existing Playwright config (`playwright-e2e.yml` / `client/playwright.config.*`) to match harness conventions (base URL, auth setup).

**Interfaces:**
- Produces: an e2e asserting the sandbox renders + isolates.

- [ ] **Step 1: Write the spec**

```ts
// client/e2e/plugin-sandbox.spec.ts
import { test, expect } from '@playwright/test';

// Assumes the existing e2e auth/setup fixtures log in as admin and that
// `storage_analytics` is enabled in the test environment. Adjust the login
// and enable steps to match the repo's existing e2e helpers.
test('plugin renders inside an opaque-origin sandbox iframe and host exposes no SDK', async ({ page }) => {
  await page.goto('/plugins/storage_analytics');

  const frame = page.locator('iframe[title="plugin-storage_analytics"]');
  await expect(frame).toHaveAttribute('sandbox', 'allow-scripts');
  const sandbox = await frame.getAttribute('sandbox');
  expect(sandbox).not.toContain('allow-same-origin');

  // The main browsing context must NOT expose the tokened SDK.
  const hasSdk = await page.evaluate(() => 'BaluHost' in window);
  expect(hasSdk).toBe(false);
});
```

- [ ] **Step 2: Run it locally if the e2e harness is available**

Run: `cd client && npx playwright test e2e/plugin-sandbox.spec.ts` (or the repo's e2e command).
Expected: PASS, or document that it runs in CI (`playwright-e2e.yml`) if local browsers aren't provisioned.

- [ ] **Step 3: Commit**

```bash
git add client/e2e/plugin-sandbox.spec.ts
git commit -m "test(plugin-sandbox): playwright e2e for sandbox isolation + no host SDK"
```

---

### Task 13: Author migration guide + ABI doc + deploy check

**Files:**
- Create: `docs/plugins/PLUGIN_AUTHOR_MIGRATION.md`
- Create: `docs/plugins/RUNTIME_ABI.md`
- Inspect: `deploy/scripts/ci-deploy.sh` (confirm the frontend build runs `npm run build`, which triggers the `prebuild` → `build:runtime`)

**Interfaces:**
- Produces: author-facing docs; a verified deploy note.

- [ ] **Step 1: Write `PLUGIN_AUTHOR_MIGRATION.md`**

Cover: the iframe sandbox model (opaque origin, no token, `postMessage` only); the `window.BaluHost` surface (`React`, `hooks`, `ui`, `icons`, `utils`, `api`, `toast`, `storage`, `navigate`, `user`); own-routes-always-allowed vs. Core scopes; declaring `api_scopes` + `min_runtime_abi` in `plugin.json`; the `storage` API (per-user, 64 KB / 100-key quota); that raw `fetch`/`localStorage`/`window.parent` do not work; building `bundle.js` against `window.BaluHost` externals. Use `optical_drive` (already compliant) and `storage_analytics` (migrated) as worked examples.

- [ ] **Step 2: Write `RUNTIME_ABI.md`**

Document `runtime_abi` (currently `1`), how the host gates on `min_runtime_abi`, and the bump policy: bump the runtime ABI when a primitive is removed/renamed or an SDK method signature changes; additive primitives don't require a bump but plugins relying on them should set `min_runtime_abi` accordingly.

- [ ] **Step 3: Verify the deploy builds the runtime**

Inspect `deploy/scripts/ci-deploy.sh` (and any frontend-build CI step). Confirm the production frontend build invokes `npm run build` (so `prebuild` → `build:runtime` emits `plugin-runtime.{js,css}` into `dist/`). If the deploy uses a custom build command that bypasses `prebuild`, add an explicit `npm run build:runtime` before it. Record the finding in `RUNTIME_ABI.md` (a "Deployment" note).

- [ ] **Step 4: Commit**

```bash
git add docs/plugins/PLUGIN_AUTHOR_MIGRATION.md docs/plugins/RUNTIME_ABI.md
git commit -m "docs(plugin-sandbox): author migration guide + runtime ABI doc"
```

---

## Final Verification

- [ ] Frontend sandbox suite: `cd client && npx vitest run src/__tests__/plugin-sandbox/` → all green.
- [ ] Frontend build (incl. runtime + CSS): `cd client && npm run build` → green; `dist/` and `public/` contain `plugin-runtime.js` + `plugin-runtime.css`.
- [ ] Typecheck: `cd client && npx tsc --noEmit` → clean.
- [ ] Backend plugin + storage tests: `cd backend && python -m pytest tests/plugins/ tests/api/test_plugin_sandbox_assets.py tests/api/test_plugin_storage_routes.py tests/api/test_plugin_ui_manifest_scopes.py -q` → green.
- [ ] Migration: `cd backend && alembic upgrade head && alembic current` → new head applied.
- [ ] Audit gap closed: `cd client && git grep -nE "pluginLoader|pluginSDK|initPluginSDK|window\.BaluHost" -- src` → no matches.
- [ ] Manual smoke (dev): `npm run build:runtime`, start dev, enable `storage_analytics`, open its page → renders in `iframe[sandbox="allow-scripts"]`, native theme, an own-route call works, a `/api/users` call is denied in the console, `window.BaluHost` is `undefined` in the main context, and `BaluHost.storage.set/get` round-trips.

---

## Self-Review (completed)

- **Spec coverage:** runtime full-surface (Task 2) + CSS (Task 3) + theme (Tasks 1/2/4) + ABI gate (Tasks 1/4/9a) + storage model/service/routes/bridge/sdk (Tasks 5–8) + migrate storage_analytics (Task 9b) + optical_drive (Task 10) + remove legacy (Task 11) + Playwright (Task 12) + docs/deploy (Task 13). All spec sections map to a task.
- **Placeholder scan:** none — every code step carries real code; Tasks 9a/6 note where to match existing fixture/model names rather than inventing them.
- **Type consistency:** `ThemePayload { name; tokens }` shared across protocol/bridge/host/runtime; `PluginBridgeOpts` gains `theme`/`minRuntimeAbi`/`onError` used identically in `PluginSandboxHost`; `setTheme` name consistent (Task 1 ↔ Task 4); storage methods `get/set/del/keys` consistent across sdk (Task 8), bridge (Task 7), and routes (Task 6); `min_runtime_abi` consistent across manifest (Phase 2), UI-manifest schema/route (Task 9a), frontend type (Task 9a), and PluginPage→host prop (Task 4).
- **Cross-task ordering note:** `index.ts` references `sdk.storage` (Task 2) which lands in Task 8, and `runtime.css` (Task 3). The plan flags this in Task 2/3/8 so the runtime build is only asserted green once Task 8 lands; commits in between stay test-green because the affected unit tests don't import `index.ts`.
