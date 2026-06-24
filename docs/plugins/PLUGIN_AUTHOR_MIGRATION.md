# Plugin Author Migration Guide

This guide is for authors migrating an existing plugin to the BaluHost sandbox runtime, or writing a new plugin from scratch. It covers the iframe isolation model, the `window.BaluHost` surface, declaring scopes and ABI requirements in `plugin.json`, the per-user storage API, and how to build your `bundle.js`.

---

## The Sandbox Model

Every plugin UI runs inside an `<iframe sandbox="allow-scripts">` served from the plugin's own route (`/api/plugins/{name}/ui/host.html`). This iframe has an **opaque origin** (`null`). The following do not work and must not be relied on:

| What you might try | Why it fails |
|---|---|
| `window.localStorage` | Isolated to the opaque origin; reads/writes are ephemeral and invisible to the host page. |
| `fetch('/api/...')` or `XMLHttpRequest` | The request carries no auth token; the backend will return 401. |
| `window.parent.document` | Cross-origin frame access is blocked by the browser. |
| `window.parent.postMessage(msg, 'https://...')` | The runtime sends to `'*'`; your plugin should never call `window.parent` directly. |
| `import React from 'react'` (bundled copy) | Wastes bytes; React is provided via `window.BaluHost.React`. |

**The only way to call the BaluHost backend is through `BaluHost.api`**, which proxies calls over `postMessage` to the host page. The host page holds the JWT and enforces scope checks before forwarding the request.

---

## The `window.BaluHost` Surface

The runtime exposes `window.BaluHost` after the host sends the `init` message. Your component will be mounted only after `window.BaluHost` is set, so it is always available inside your component tree.

### React and hooks

```js
const { React, hooks } = window.BaluHost;
const { useState, useEffect, useCallback, useMemo, useRef,
        useContext, createContext, memo, forwardRef } = hooks;
```

These are the same React 18 instances used by the host page, so context and hook rules work normally.

### UI primitives (`BaluHost.ui`)

Pre-styled components that automatically follow the host theme (dark / light / custom). Use these instead of writing raw HTML with Tailwind classes.

| Export | Description |
|---|---|
| `Button` | Standard button, supports `variant`, `size`, `disabled` |
| `Card`, `CardHeader`, `CardContent`, `CardFooter` | Content card layout |
| `Badge` | Status / label badge |
| `Modal` | Accessible modal dialog |
| `Input` | Text input |
| `Textarea` | Multi-line text area |
| `Select` | Dropdown select |
| `ProgressBar` | Horizontal progress indicator |
| `Spinner` | Inline loading spinner |
| `LoadingOverlay` | Full-area loading overlay |
| `EmptyState` | Empty content placeholder with icon + message |
| `Tabs`, `TabPanel` | Tabbed navigation |
| `ByteSizeInput` | Byte-aware number input (shows GiB/GB) |

```js
const { Button, Card, CardContent, Spinner } = window.BaluHost.ui;
```

### Icons (`BaluHost.icons`)

Full Lucide icon set. Import by name:

```js
const { HardDrive, Disc, AlertCircle } = window.BaluHost.icons;
```

### Utilities (`BaluHost.utils`)

| Function | Signature | Description |
|---|---|---|
| `formatBytes` | `(bytes: number) => string` | Human-readable byte size (`"4.2 GiB"`) |
| `formatDate` | `(date: string \| Date, opts?) => string` | Locale-aware date/time string |
| `formatDuration` | `(seconds: number) => string` | `"m:ss"` format |
| `formatUptime` | `(seconds: number) => string` | `"2d 4h"` / `"35m"` / `"42s"` |
| `cn` | `(...classes) => string` | Conditional class name joiner |

### SDK methods (proxied over postMessage)

#### `BaluHost.api` — HTTP calls to the backend

```js
// All methods return a Promise that resolves to the parsed JSON body.
BaluHost.api.get(url)                // GET
BaluHost.api.post(url, body)         // POST
BaluHost.api.put(url, body)          // PUT
BaluHost.api.patch(url, body)        // PATCH
BaluHost.api.delete(url)             // DELETE
```

Calls time out after 30 seconds. Disallowed URLs reject with `{ code: 'scope_denied' }`.

#### `BaluHost.toast` — user notifications

```js
BaluHost.toast.success('Disc ejected.')
BaluHost.toast.error('Drive not found.')
```

#### `BaluHost.navigate` — in-app navigation

```js
// Only within your own plugin's sub-routes.
BaluHost.navigate('/plugins/optical_drive/discs/1')
```

Navigating outside your plugin's path prefix will be rejected.

#### `BaluHost.storage` — per-user persistent key/value store

See the [Storage API](#the-storage-api) section below.

### Current user (`BaluHost.user`)

```js
const { user } = window.BaluHost;
// { id: number, username: string, role: string }
```

---

## Allowed API Routes

The bridge enforces two rules for every `BaluHost.api` call:

1. **Own routes** — any path that starts with `/api/plugins/{your-plugin-name}/` is always allowed (GET, POST, PUT, PATCH, DELETE).
2. **Core routes** — any other `/api/...` path requires a matching scope declared in `plugin.json` and granted by the user.

### Core scope catalog (v1)

| Scope key | Allowed paths | Methods |
|---|---|---|
| `read:system-info` | `/api/system/info` | GET |
| `read:storage` | `/api/files/storage/**`, `/api/system/storage/**` | GET |
| `read:power` | `/api/power/**` | GET |

Sensitive routes (`/api/users`, `/api/auth`, `/api/admin`, etc.) are not in the catalog and cannot be opened by any scope. The sandbox will log a console warning and post a scope-denied audit entry for every blocked call.

---

## Declaring `api_scopes` and `min_runtime_abi` in `plugin.json`

```json
{
  "manifest_version": 1,
  "name": "my_plugin",
  "version": "1.0.0",
  "display_name": "My Plugin",
  "min_baluhost_version": "1.37.0",
  "api_scopes": ["read:system-info"],
  "min_runtime_abi": 1,
  "ui": { "bundle": "ui/bundle.js", "styles": null }
}
```

- `api_scopes`: list of Core scope keys your plugin needs. Users see this list in the plugin enable dialog. The values are persisted as `granted_api_scopes` and compared at call time.
- `min_runtime_abi`: minimum runtime ABI version your bundle requires. If the installed runtime is older, the host renders "This plugin needs a newer BaluHost runtime." instead of the iframe. Set this to the ABI at which the primitive you depend on was introduced. Currently `1` is the only ABI version.

---

## The Storage API

`BaluHost.storage` is a per-user, per-plugin key/value store backed by the BaluHost database. It is fully isolated: user A's entries are not visible to user B.

```js
// Store a value (any JSON-serializable value)
await BaluHost.storage.set('last_scan', { ts: Date.now(), count: 42 });

// Retrieve (returns undefined if the key does not exist)
const data = await BaluHost.storage.get('last_scan');

// List all keys owned by this plugin for the current user
const keys = await BaluHost.storage.keys();   // string[]

// Delete a key
await BaluHost.storage.del('last_scan');
```

**Quota**: 64 KB per value (JSON-serialized), 100 keys per (plugin, user) pair. Exceeding either limit rejects with `{ code: 'storage_quota' }`.

There is no `localStorage`, `IndexedDB`, or `sessionStorage` available in the sandbox that persists across page loads — use `BaluHost.storage` for everything you need to persist.

---

## Building `bundle.js`

Your plugin's frontend must:

1. **Declare `window.BaluHost` as external** so React and the SDK are not bundled in.
2. **Export the root component as the default export** — the runtime calls `mod.default` (or falls back to `mod.Plugin`).

### Vite example (`vite.config.js`)

```js
import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    lib: {
      entry: 'src/index.jsx',
      formats: ['es'],
      fileName: () => 'bundle.js',
    },
    rollupOptions: {
      // Treat the entire BaluHost surface as external.
      external: ['baluhost'],
      output: {
        globals: { baluhost: 'BaluHost' },
      },
    },
  },
});
```

Inside your source code, reference the surface through the global:

```js
// src/index.jsx
const { React, hooks, ui } = window.BaluHost;
const { useState, useEffect } = hooks;
const { Button, Card } = ui;

export default function MyPlugin({ user }) {
  const [items, setItems] = useState([]);
  // ...
  return <Card>...</Card>;
}
```

The runtime mounts `mod.default` (your component) and passes `{ user }` as props.

---

## Worked Examples

### `optical_drive` — Already Compliant

The `optical_drive` plugin was written from the start for the sandbox runtime. Its `plugin.json` already declares `api_scopes: []` (it only calls its own routes) and `min_runtime_abi: 1`. No migration needed.

```json
{
  "api_scopes": [],
  "min_runtime_abi": 1,
  "ui": { "bundle": "ui/bundle.js", "styles": null }
}
```

Its bundle uses `window.BaluHost.React` / `window.BaluHost.api.get('/api/plugins/optical_drive/...')` exclusively. This is the reference pattern.

---

### `storage_analytics` — Migrated

`storage_analytics` was a pre-sandbox plugin. Here is a before/after summary of the migration.

#### Before (pre-sandbox)

```js
// BEFORE: ran in the main page — token in localStorage, direct fetch
import React, { useState, useEffect } from 'react';  // bundled copy

export default function StorageAnalytics() {
  const token = localStorage.getItem('token');        // does not work in sandbox

  useEffect(() => {
    fetch('/api/plugins/storage_analytics/stats', {   // unauthenticated in sandbox
      headers: { Authorization: `Bearer ${token}` },
    }).then(r => r.json()).then(setData);
  }, []);
  // ...
}
```

#### After (sandbox-compliant)

```js
// AFTER: uses window.BaluHost — no bundled React, no token, no raw fetch
const { React, hooks, ui } = window.BaluHost;
const { useState, useEffect } = hooks;
const { Card, CardContent, Spinner } = ui;

export default function StorageAnalytics() {
  const [data, setData] = useState(null);

  useEffect(() => {
    BaluHost.api.get('/api/plugins/storage_analytics/stats')   // proxied, authenticated, own-route
      .then(setData)
      .catch(() => BaluHost.toast.error('Failed to load storage data'));
  }, []);

  if (!data) return <Spinner />;
  return <Card><CardContent>...</CardContent></Card>;
}
```

`plugin.json` changes:

```diff
+  "api_scopes": [],
+  "min_runtime_abi": 1
```

`storage_analytics` only calls its **own** routes (`/api/plugins/storage_analytics/*`), which are always allowed, so `api_scopes` stays `[]`. A plugin that needs a **Core** route — e.g. `GET /api/files/storage` — must instead declare the matching catalog scope, `"api_scopes": ["read:storage"]`, and have it admin-granted at install.

**Key changes summary:**

| Old pattern | New pattern |
|---|---|
| `import React from 'react'` | `const { React, hooks } = window.BaluHost` |
| `localStorage.getItem('token')` | Removed — no token needed |
| `fetch('/api/plugins/storage_analytics/stats', { headers: ... })` | `BaluHost.api.get('/api/plugins/storage_analytics/stats')` |
| No scope declaration | `"api_scopes": []` (own-routes need no scope) |
| localStorage for persistence | `BaluHost.storage.set/get` |

---

## Quick Checklist

- [ ] `window.BaluHost` used for all React, hooks, UI primitives, icons, and utils.
- [ ] No `import React` or other host-page modules bundled.
- [ ] No `localStorage`, `sessionStorage`, or `IndexedDB` for persisting data — use `BaluHost.storage`.
- [ ] No raw `fetch` or `XMLHttpRequest` to `/api/...` — use `BaluHost.api`.
- [ ] No `window.parent` access.
- [ ] `plugin.json` lists all needed Core scopes in `api_scopes`.
- [ ] `plugin.json` sets `min_runtime_abi` to the ABI version at which required primitives were introduced (currently `1`).
- [ ] `bundle.js` exported as ES module with `export default MyComponent`.
