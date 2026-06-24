# Plugin Frontend Sandbox — Phases 3–5 (Runtime UI/Theme/Storage, Migration, E2E)

**Status:** Spec
**Date:** 2026-06-24
**Track:** A (Frontend JS isolation) of the Plugin-Sandboxing program — the follow-up to Phases 1–2.
**Parent spec:** `docs/superpowers/specs/2026-06-22-plugin-frontend-iframe-sandbox-design.md`
**Parent plan (Phases 1–2, merged in PR #278):** `docs/superpowers/plans/2026-06-22-plugin-frontend-iframe-sandbox.md`
**Delivery:** a single PR (`feat/plugin-sandbox-phase3-5`), one combined implementation plan.

## Context — where Phases 1–2 left us

Merged on `main` (verified against the code, not the stale vectordb index):

- `client/src/components/PluginPage.tsx` renders `<PluginSandboxHost>` → opaque-origin `<iframe sandbox="allow-scripts">` + `PluginBridge` + default-deny scope policy.
- Backend: generated `GET /api/plugins/{name}/ui/host.html` bootstrap (framable carve-out in `SecurityHeadersMiddleware`), permissive CORS on `ui/` assets, manifest `api_scopes` + `min_runtime_abi`, `InstalledPlugin.granted_api_scopes` column + migration, grant-at-install, `scope_denied` audit route.
- In-iframe runtime skeleton (`client/src/plugin-runtime/`): `createSandboxSdk` proxies `api`/`toast`/`navigate` over `postMessage`; `index.ts` boots, announces `ready`, builds a minimal `window.BaluHost`, loads `bundle.js`. Built by `vite.runtime.config.ts` into `client/public/plugin-runtime.js` (gitignored), served at `/plugin-runtime.js`.

**The deliberate debt this spec closes:** `client/src/main.tsx` still calls `initPluginSDK()` → a tokened `window.BaluHost` lives in the **main browsing context** (`client/src/lib/pluginSDK.ts`), and `client/src/lib/pluginLoader.ts` (the old `import()` path) still exists. Sandbox plugins can't reach them, but the audit gap ("main context exposes the full tokened SDK") is only closed once these are removed (Phase 4).

## Decisions (this spec's purpose)

These resolve the open questions the parent spec deferred:

1. **Storage = server-side, own table, scoped per `(plugin, user)`.** Persistent, multi-user-clean, device-independent. Each user has their own plugin state; no cross-user read/write.
2. **Runtime UI surface = the full primitive set.** Bundle React + hooks + **all** `ui/` primitives + lucide icons + utils into `plugin-runtime.js`, matching the old SDK shape 1:1, so hand-written plugin bundles run unchanged where they already consumed `window.BaluHost`.
3. **CSS = a separate cacheable asset** (`plugin-runtime.css`) linked from `host.html`, not inlined into the JS.
4. **Phase 4 is far smaller than the parent spec implied** (see Finding below): no Vite build to re-target — the bundled plugins are hand-written plain-JS files; only 2 have UI.

### Finding that reshapes Phase 4

The three "bundled plugins" live in-repo at `backend/app/plugins/installed/{name}/`:

- `tapo_smart_plug` — **no `ui/` directory at all** (backend-only plugin). Nothing to migrate.
- `optical_drive/ui/bundle.js` — a **hand-written plain-JS file** (`// bundle_fixed.js`) that already destructures `window.BaluHost` (`React, ui, icons, toast, api, utils`). No build pipeline; the file *is* the source.
- `storage_analytics/ui/bundle.js` — a hand-written placeholder that uses `window.React` directly **and a raw `fetch`** helper (its own comment: "In production, this would be built with Vite/webpack…"). Raw `fetch` cannot work from the opaque-origin iframe (no token, CORS-blocked), so this one needs real porting to `BaluHost.api`.

So Phase 4 = edit 2 JS files + 2 `plugin.json` files + delete legacy, **not** re-target an externals build.

## Architecture (unchanged contract, extended runtime)

```
PluginPage → PluginSandboxHost → <iframe sandbox="allow-scripts">   (opaque origin, Phases 1–2)
                                    host.html  (backend-served bootstrap)
                                    ├── plugin-runtime.css   ← NEW: compiled Tailwind + theme base
                                    ├── plugin-runtime.js    ← EXTENDED: React + ui + icons + utils + storage
                                    └── bundle.js            (plugin; consumes window.BaluHost externals)
                                           │  postMessage RPC (the only egress)
                                           ▼
                                    PluginBridge (host; real token; api/toast/navigate/storage policy)
```

No change to the isolation model: opaque origin, reference-equality `event.source` check, no token in the iframe, `postMessage` the sole channel.

---

## Phase 3a — Runtime UI lib + theme

### `window.BaluHost` (in-iframe), final shape

```ts
window.BaluHost = {
  React, hooks,                          // real React bundled in the runtime (iframe's own instance)
  ui: { Button, Card, CardHeader, CardContent, CardFooter, Badge, Modal, Input,
        Textarea, Select, ProgressBar, Spinner, LoadingOverlay, EmptyState,
        Tabs, TabPanel, ByteSizeInput },  // the full existing primitive set
  icons,                                 // lucide-react
  utils: { formatBytes, formatDate, formatDuration, formatUptime, cn },
  toast,                                 // → postMessage proxy (channel 'toast')
  api,                                   // → postMessage proxy (channel 'api'), NO token
  storage,                               // → postMessage proxy (channel 'storage'), per-(plugin,user)
  navigate,                              // → postMessage proxy (channel 'navigate'), prefix-bounded
  user,                                  // from init handshake (id/username/role, read-only)
}
```

The shape mirrors the old `initPluginSDK` (`pluginSDK.ts`) exactly, minus the security-sensitive internals (no `apiClient`, no `localStorage`, no token). The `ui/` primitives are **pure** (verified: e.g. `Modal.tsx` imports only React; primitives are styled via Tailwind classes + CSS variables, no host context), so they render standalone in the iframe.

### Build

- The runtime entry (`client/src/plugin-runtime/index.ts` / a new `runtimeSdk` assembly) imports React, the `ui/` primitives, `lucide-react`, and the `utils`, and assembles `window.BaluHost` on `init` (replacing the current minimal `{api,toast,navigate,user}`).
- `vite.runtime.config.ts` stays a single-IIFE lib build but now also emits a CSS asset.
- Plugin bundles keep React/ui as externals (`window.BaluHost`) — small bundles, no duplicate React. (Already true for the hand-written bundles.)

### CSS delivery

- The runtime entry imports the host's compiled Tailwind + a theme-base stylesheet; Vite emits `client/public/plugin-runtime.css` next to `plugin-runtime.js` (both gitignored build outputs).
- The backend `host.html` generator adds `<link rel="stylesheet" href="/plugin-runtime.css">` to `<head>`, served at root in dev (Vite public) and prod (copied into `dist/`), same permissive-CORS story as the JS (no credentials).

### Theme

- The `init` push payload gains `theme: { mode: 'light' | 'dark', tokens: Record<string, string> }`, sourced from the host `ThemeContext` (the CSS-variable token map currently applied to `:root`).
- The runtime applies `tokens` to `document.documentElement.style` and sets a `data-theme`/class for `mode` → native look + dark mode inside the frame.
- A `theme-changed` push (already a declared `HOST_PUSHES` name) re-applies tokens live when the host theme switches; `PluginSandboxHost` subscribes to `ThemeContext` and forwards changes.

---

## Phase 3b — Storage channel + backend

### Data model

New table `plugin_storage`:

| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `plugin_name` | str, indexed | |
| `user_id` | int FK `users.id`, indexed | per-user scoping |
| `key` | str | |
| `value` | JSON / Text | structured-clone-safe value from the plugin |
| `updated_at` | datetime | |

Unique constraint `(plugin_name, user_id, key)`. Alembic migration chained onto the real `alembic heads` (see `project_alembic_migration_head_pitfall`).

### Routes (own-namespace, authenticated as the calling user)

- `GET    /api/plugins/{name}/_storage/{key}` → `{ value }` or 404
- `PUT    /api/plugins/{name}/_storage/{key}` body `{ value }` → upsert
- `DELETE /api/plugins/{name}/_storage/{key}` → 204
- `GET    /api/plugins/{name}/_storage` → `{ keys: string[] }`

All scoped to `current_user.id` server-side; a user can never read another user's plugin state. These are the plugin's **own routes** (`/api/plugins/{name}/…`), so the existing default-deny bridge policy already permits them — no new scope, no catalog change. Rate-limited like the other plugin routes. The `_storage` segment gets the same exact-route carve-out treatment as the existing `_audit` route (so it isn't shadowed by the generic `ui/{file_path}` handler).

### Bridge wiring

- `PluginBridge.dispatch` gains a `storage` case: `get(key)` → `GET`, `set(key,value)` → `PUT`, `del(key)` → `DELETE`, `keys()` → `GET …/_storage`, all via `apiClient` (real token), returning only the JSON body.
- The in-iframe `createSandboxSdk` gains a `storage` object mirroring those methods over the `storage` channel.

### Quota

- Value size ≤ **64 KB** (serialized), ≤ **100 keys** per `(plugin, user)`. Over-limit → reject `{ code: 'storage_quota', message }`. Enforced server-side (authoritative) and surfaced through the rejected RPC.

---

## Phase 4 — Migrate the UI plugins + remove legacy

### Migrate (2 plugins with UI)

- **`optical_drive`**: already consumes `window.BaluHost` (React/ui/icons/toast/api/utils) → works under the iframe runtime essentially as-is. Add `api_scopes` + `min_runtime_abi: 1` to `plugin.json`; audit every `api.*` call to confirm it targets own-routes or a granted scope (re-point any Core call onto its own backend route or a declared scope).
- **`storage_analytics`**: port `window.React` → `BaluHost.React` and the raw `fetch` helper → `BaluHost.api` (raw fetch is CORS/credential-blocked in the opaque-origin frame). Add `api_scopes` + `min_runtime_abi: 1`.
- **`tapo_smart_plug`**: no `ui/` → no migration; note explicitly in the plan and PR.

The two migrated plugins double as the end-to-end reference implementation.

### Remove legacy (closes the audit gap)

- Delete `client/src/lib/pluginLoader.ts` (the `import()` path) and `client/src/lib/pluginSDK.ts` (`initPluginSDK`, the main-context SDK).
- Remove the `initPluginSDK` import + call from `client/src/main.tsx`, and drop the `window.BaluHost` / `window.BaluHostPlugins` ambient typings.
- Result: `window.BaluHost` no longer exists in the host browsing context. Grep the client for any remaining `pluginLoader` / `pluginSDK` / `initPluginSDK` / `window.BaluHost` references and clean them up.

---

## Phase 5 — E2E + docs

- **Playwright** (`client` e2e): enable a plugin, assert its page renders an `iframe[sandbox="allow-scripts"]` **without** `allow-same-origin`; assert one allowed own-route call succeeds and one `/api/users` call is denied; assert `window.BaluHost === undefined` in the **main** context.
- **Plugin-author migration guide**: the `window.BaluHost` surface (`React`/`hooks`/`ui`/`icons`/`utils`/`api`/`toast`/`storage`/`navigate`/`user`), the no-token model, own-routes-vs-scopes, `api_scopes` declaration, the externals build expectation.
- **ABI doc**: `runtime_abi` / `min_runtime_abi` semantics and the bump policy (a new primitive or breaking SDK change ⇒ bump).
- **Deploy**: confirm the production frontend build runs `build:runtime` (the `prebuild` hook does locally; verify the deploy pipeline invokes the same `npm run build` so `plugin-runtime.{js,css}` land in `dist/`).

---

## ABI versioning + error handling

- `runtime_abi = 1` constant in the runtime, reported in the `ready` event payload. The host compares it against the manifest's `min_runtime_abi` at `init`; if `min_runtime_abi > runtime_abi`, the host shows a clean "this plugin needs a newer BaluHost runtime" state and does **not** load `bundle.js`.
- Error codes surfaced via rejected RPC / host error UI: `storage_quota`, `timeout`, `scope_denied`, `unknown_channel`, `abi_mismatch`.

## Testing

- **Phase 3 — frontend (vitest):** storage SDK proxy (`get/set/del/keys` round-trip + timeout), bridge `storage` dispatch (maps to apiClient verbs, returns body), theme handshake (init applies tokens; `theme-changed` re-applies), full `window.BaluHost` shape assembled on `init`.
- **Phase 3 — backend (pytest):** `plugin_storage` CRUD, per-`(plugin,user)` isolation (user A cannot read user B), quota (size + key-count) rejections, migration applies on the real head.
- **Phase 4:** the 2 migrated plugins load and render in the sandbox; backend suite stays green; a client grep confirms zero `pluginLoader`/`pluginSDK`/`window.BaluHost` references remain.
- **Phase 5:** the Playwright scenario above.

## Out of scope (unchanged from the parent spec)

Backend Python isolation (Track B), supply-chain signing (Track C), separate-origin iframe, write-scopes/wildcard scopes on Core routes, plugin-to-plugin calls, per-plugin in-frame CSP tightening.

## Risks / watch-items

- **`host.html` carve-out** in `SecurityHeadersMiddleware` must keep covering the bootstrap; adding the `<link>` doesn't change that path.
- **`_storage` route shadowing**: register/guard it like the existing `_audit` exact-route carve-out so the generic `ui/{file_path}` asset handler doesn't swallow it.
- **CSS in opaque-origin iframe**: the stylesheet loads via `<link>` with permissive CORS and no credentials — verify it actually applies inside the null-origin document (it should; stylesheets aren't origin-gated for rendering).
- **Stale vectordb index**: the search index predates the PR #278 merge — trust the files, and refresh the index before relying on semantic search for this work.
