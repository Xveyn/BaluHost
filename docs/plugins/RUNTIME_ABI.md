# Plugin Runtime ABI

This document describes the runtime ABI versioning scheme for the BaluHost plugin sandbox, how the host gates plugin loading on the manifest's `min_runtime_abi` field, and the policy for bumping the ABI version.

---

## Current ABI

**`RUNTIME_ABI = 1`**

Defined in `client/src/plugin-runtime/index.ts`:

```ts
const RUNTIME_ABI = 1;
```

This constant is announced to the host page in the first `postMessage` the runtime sends:

```ts
window.parent.postMessage(
  { kind: 'event', name: 'ready', payload: { runtime_abi: RUNTIME_ABI } },
  '*',
);
```

---

## How the Host Gates on `min_runtime_abi`

### Handshake sequence

1. The host renders `<iframe sandbox="allow-scripts" src="/api/plugins/{name}/ui/host.html">`.
2. The runtime boots inside the iframe, loads `bundle.js`, and sends `ready` with `{ runtime_abi: 1 }`.
3. `PluginBridge` (in `client/src/lib/plugin-sandbox/hostBridge.ts`) receives the `ready` event and checks:

```ts
const abi = typeof runtimeAbi === 'number' ? runtimeAbi : 1;
if (this.opts.minRuntimeAbi !== undefined && abi < this.opts.minRuntimeAbi) {
  this.opts.onError?.('abi_mismatch');
  return;
}
```

4. If the runtime ABI is below `minRuntimeAbi`, the bridge calls `onError('abi_mismatch')` and does **not** send `init`. The plugin is never mounted.
5. `PluginSandboxHost` (in `client/src/components/plugins/PluginSandboxHost.tsx`) handles the error:

```tsx
if (error === 'abi_mismatch') {
  return (
    <div className="p-6 rounded-lg border border-amber-500/40 bg-amber-500/10 text-amber-200 text-sm">
      This plugin needs a newer BaluHost runtime.
    </div>
  );
}
```

### Where `minRuntimeAbi` comes from

`PluginSandboxHost` receives `minRuntimeAbi` as a prop from `PluginPage`, which reads it from the plugin's UI manifest served at `/api/plugins/{name}/ui-manifest`. The manifest is derived from `plugin.json`'s `min_runtime_abi` field.

---

## ABI Bump Policy

### Bump the ABI when

- A primitive is **removed** from `window.BaluHost` (e.g., a UI component is deleted).
- A primitive is **renamed** (e.g., `Button` → `PrimaryButton`).
- An SDK method **signature changes incompatibly** (e.g., `api.get(url)` gains a required second argument).
- A `storage` method is removed or its error contract changes.

A bump means incrementing `RUNTIME_ABI` in `index.ts` (e.g., `1` → `2`). Any plugin with `min_runtime_abi: 2` will then refuse to load on a host serving runtime ABI 1, showing the "needs a newer runtime" message until the host is updated.

### Do NOT bump the ABI when

- A **new** UI primitive is added to `window.BaluHost.ui`.
- A **new** icon is added to `window.BaluHost.icons`.
- A **new** utility is added to `window.BaluHost.utils`.
- A **new** SDK method or channel is added.
- The runtime's internal implementation changes without affecting the surface.

Additive changes are backward-compatible: older plugins simply do not use the new primitive and continue to work.

### Declaring a dependency on a new primitive

If your plugin relies on a primitive that was introduced at a specific ABI version, set `min_runtime_abi` in `plugin.json` to that version. This ensures the plugin does not load silently broken on an older host:

```json
{
  "min_runtime_abi": 2
}
```

If you do not set `min_runtime_abi`, it defaults to `1` and the plugin will load on any runtime. Only set it higher if you know you use a primitive that did not exist in ABI 1.

### ABI history

| ABI | Introduced | Notes |
|---|---|---|
| `1` | BaluHost 1.37.0 | Initial sandbox runtime. Full surface: React 18, hooks, ui (15 primitives), icons (Lucide), utils (5 functions), api (5 methods), toast, navigate, storage (4 methods), user. |

---

## Deployment

### How the runtime reaches production

The plugin runtime is built as a separate Vite library bundle (`plugin-runtime.js` + `plugin-runtime.css`) via the `build:runtime` script in `client/package.json`:

```json
"build:runtime": "vite build --config vite.runtime.config.ts",
"prebuild": "npm run build:runtime",
"build": "tsc -b && vite build"
```

The `prebuild` lifecycle hook runs automatically before `npm run build`. This means whenever the main frontend build runs, the runtime bundle is (re)built first and emitted into `dist/` and `public/` before Vite processes the host application.

### Deploy script verdict

`deploy/scripts/ci-deploy.sh`, step 6 (Frontend Build):

```bash
cd "$INSTALL_DIR/client"
npm ci
npm run build
```

**The deploy script invokes `npm run build` — not `vite build` directly.** This means the `prebuild` hook fires, `build:runtime` runs first, and `plugin-runtime.{js,css}` are emitted before the host application build. The runtime bundle is included in every production deploy.

**No bypass risk.** The `build:prod` script (`"vite build"` — no `tsc`, no `prebuild` hook) exists in `package.json` but is **not used** by `ci-deploy.sh`. The deploy script uses `npm run build` exclusively. Authors building locally for distribution should also use `npm run build` (not `npm run build:prod` or `vite build` directly) to ensure the runtime is up to date.
