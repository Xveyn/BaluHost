# Plugin Frontend Sandbox — iframe + postMessage Bridge

**Status:** Spec
**Date:** 2026-06-22
**Track:** A (Frontend JS isolation) of the Plugin-Sandboxing program. Tracks B (backend Python isolation) and C (supply-chain signing) are separate specs.
**Audit origin:** `SECURITY_AUDIT_2026-06-14.md` — "Plugin-System = größtes Architektur-Risiko". Closes the deferred Non-Goal "Frontend SDK changes / sandboxing" from `2026-04-13-plugin-marketplace-design.md`.

## Problem

Today a plugin's `ui/bundle.js` is loaded via `import(/* @vite-ignore */ bundleUrl)` directly into the **main browsing context** (`client/src/lib/pluginLoader.ts:41`, consumed only by `client/src/components/PluginPage.tsx:57`). The plugin's default export is a React component rendered into the host React tree. Plugins receive the full `window.BaluHost` SDK (`client/src/lib/pluginSDK.ts`), which exposes `api` — a wrapper over `apiClient` that auto-attaches the user's Bearer token from `localStorage`.

Consequences for **untrusted, third-party** plugin code (the agreed trust model — a real third-party ecosystem):

- A malicious plugin can read `localStorage` (the JWT), call **any** `/api/*` endpoint as the logged-in user, manipulate the host DOM, and exfiltrate data. This is a stored-XSS / account-takeover equivalent.
- The plugin runs in **every** user's browser that opens its page, with that user's privileges.
- `window.BaluHost` is a writable global (`pluginSDK.ts:237`); `loadPluginStyles` injects an unrestricted `<link>` (`pluginLoader.ts:122`).

Goal of this spec: run plugin frontend code in a **browser-enforced sandbox** with no access to the host token, host storage, host DOM, or arbitrary API endpoints — while keeping the existing plugin authoring experience (`window.BaluHost` with React + UI components) largely intact.

## Trust Model & Scope

- **Threat model** (from the audit): VPN-only access, single-admin home NAS, potentially multiple non-admin LAN users. Plugin **install** is admin-only; plugin **UI** executes in any user's browser who opens it. Plugins are untrusted third-party code.
- **The entire untrusted-JS surface in the frontend is one component**: `PluginPage.tsx` (verified — sole consumer of the bundle loader). Everything else is in scope only as it touches that path.
- **Dashboard panels are already safe** and out of scope: a plugin supplies a declarative `PanelSpec` (`gauge`/`stat`/`status`/`chart` + data) and the **host** renders it with built-in renderers (`client/src/components/dashboard/PluginDashboardPanel.tsx` + `panels/*`). No plugin JS executes.

### Non-Goals (explicit)

- **Backend Python isolation** — plugin `__init__.py` keeps running in-process. That is Track B.
- **Supply-chain signing / provenance** — Track C.
- **Separate-origin iframe** (real distinct domain/port) — a future hardening over the opaque-origin sandbox chosen here; needs DNS/cert/port plumbing on the LAN/VPN box.
- **Write access to sensitive Core endpoints from plugins** — no `write:*` or wildcard API scopes in v1.
- **Plugin-to-plugin calls.**

## Approach Selection

For untrusted code, three isolation strategies were weighed:

1. **Soft-sandbox in the main context** (SES/`lockdown`, Proxy-hidden globals) — JS soft-sandboxes are bypassable; does not meet the untrusted-code bar. Rejected.
2. **Web Worker** — strong isolation but no DOM access; would require a full declarative-UI protocol (a custom renderer over `postMessage`). Too heavy for UI plugins. Rejected.
3. **Sandboxed `<iframe>` + `postMessage` RPC** — browser-enforced isolation, DOM rendering preserved inside the frame. **Chosen.**

## Architecture

```
PluginPage  (host chrome: title + PluginBadge + loading/error states)
└── PluginSandboxHost  (owns the iframe + the bridge)
        └── <iframe sandbox="allow-scripts">          ← NO allow-same-origin → opaque (null) origin
                host.html            (backend-served sandbox bootstrap)
                ├── plugin-runtime.js (host-built: React + UI lib + theme CSS + bridge SDK)
                └── bundle.js         (plugin, built against window.BaluHost externals)
                         │
                         │  postMessage RPC  (the ONLY channel out)
                         ▼
                Host bridge  (holds the real token; enforces API policy)
```

### Why this isolates (browser-enforced, not hand-rolled)

- `sandbox="allow-scripts"` **without** `allow-same-origin` gives the iframe document an **opaque origin**. It cannot reach `parent`/host DOM, host `localStorage`, or host cookies. (It also cannot use its own `localStorage` — fine; plugin persistence goes through the `storage` bridge channel.)
- The plugin holds **no token**. A direct `fetch('/api/...')` from the null-origin iframe is cross-origin **without** credentials → 401, and CORS blocks reading the response. The **only** way out is `postMessage`.
- **Origin check on the host:** a null-origin frame posts with `event.origin === "null"`, so the host validates by **reference equality** `event.source === iframe.contentWindow`, not by origin string.

### Asset loading

`host.html`, `plugin-runtime.js`, and `bundle.js` are not secret. The plugin `ui/` asset routes serve them with permissive CORS (`Access-Control-Allow-Origin: *`) so the opaque-origin iframe can load them via `<script>` / `import()`. No credentials are involved in these requests.

## The Bridge (postMessage RPC protocol)

`PluginSandboxHost` (new, `client/src/components/plugins/`) replaces the `loadPluginComponent` path. It renders the iframe, holds its `contentWindow` reference, and mediates every message.

### Lifecycle / handshake

```
1. Host renders <iframe sandbox="allow-scripts" src="/api/plugins/{name}/ui/host.html">
2. runtime.js loads → postMessage(parent, {kind:'event', name:'ready'})      [iframe→host]
3. Host replies {kind:'push', name:'init', payload:{user, pluginName, theme, locale, i18n}}
4. runtime builds window.BaluHost, loads bundle.js, renders the default export
5. Running: RPC calls + events (below)
6. Unmount: host removes the iframe → all pending RPCs reject
```

### Message envelope (one shape for everything)

```ts
// iframe → host (request, expects a reply)
{ kind:'rpc', id:string, channel:'api'|'toast'|'navigate'|'storage', method:string, args:unknown[] }
// host → iframe (reply)
{ kind:'rpc-result', id:string, ok:boolean, value?:unknown, error?:{code:string, message:string} }
// iframe → host (fire-and-forget)
{ kind:'event', name:'resize'|'ready'|'error', payload:unknown }
// host → iframe (push)
{ kind:'push', name:'init'|'theme-changed'|'visibility', payload:unknown }
```

### Mediated channels — the entire plugin capability surface (deliberately small)

| Channel | What the plugin may do | Host enforcement |
|---|---|---|
| `api` | `get/post/put/patch/delete(url, data)` | **API policy** (below), then fetch with the real token |
| `toast` | success/error/loading/dismiss | forwarded to `react-hot-toast` |
| `navigate` | navigation **only within** `/plugins/{name}` | host validates target path prefix |
| `storage` | get/set/del — namespaced key-value | host persists under the plugin's own scope (backend route, or a bounded host-localStorage prefix) |
| `resize` (event) | reports content height | host sets iframe height (no inner scrollbar) |

Anything not in this set does not exist for plugins.

### Robustness

- Every RPC carries an `id` + a timeout (30 s) → no hanging promises.
- The host **whitelists** `channel`+`method`; unknown values reject (no dynamic dispatch).
- Args cross the boundary as plain JSON (structured clone) — no functions/prototypes.
- A message flood is rate-limited / dropped to protect the host thread (DoS guard).

## In-iframe Runtime & SDK (`window.BaluHost`, new)

`plugin-runtime.js` is **built and served by the host** and runs inside the iframe. It presents the same `window.BaluHost` shape as today, but the security-sensitive parts are now bridge proxies.

```ts
window.BaluHost = {
  React, hooks,                          // real React instance INSIDE the iframe (bundled in the runtime)
  ui: { Button, Card, Modal, … },        // existing UI lib, rendered standalone in the iframe
  icons,                                 // lucide
  utils: { formatBytes, cn, … },         // pure functions, unchanged
  toast,                                 // → postMessage proxy (channel 'toast')
  api:   { get,post,put,patch,delete },  // → postMessage proxy (channel 'api'), NO token
  storage,                               // → postMessage proxy (channel 'storage'), namespaced
  navigate,                              // → postMessage proxy (channel 'navigate'), prefix-bounded
  user,                                  // from init handshake (id/username/role, read-only)
}
```

### Differences from today (= the plugin-author migration cost)

- `api` is async-identical to today (`await BaluHost.api.get(url)`) → plugin JSX/logic mostly unchanged. No direct `apiClient`/`localStorage`/`window` access (never officially in the SDK anyway).
- React is the iframe's **own** instance (bundled in the runtime), not the host's. Transparent for plugins that take React from `BaluHost.React`/`hooks` (the documented path).
- Styling: the runtime ships the host's compiled Tailwind/theme CSS into the iframe and applies theme tokens (CSS variables) from the `init` handshake → native look & dark mode.

### Build / distribution

- The runtime is a separate client-build entry (`vite` lib mode), versioned (`runtime_abi: 1`), served from a host route.
- Plugin `bundle.js` is built with React/ui as **externals** (`window.BaluHost`) — small bundles, no duplicate React (unchanged from today).
- ABI check: the runtime reports `runtime_abi`; a manifest may declare `min_runtime_abi` → a clean error instead of a cryptic break.

## API Mediation & Permission Scopes (default-deny)

The `api` channel is the only path to data; least-privilege lives here.

### Per-call policy (host bridge)

```
1. Normalize the target URL (resolve, no '..', must start with /api/).
2. Own routes:  /api/plugins/{thisPlugin}/...   → ALWAYS allowed.
3. Otherwise (Core route) → allowed only if a plugin-declared AND admin-granted
   scope matches it (allowlist lookup). Else → reject {code:'scope_denied'}.
4. Allowed → host fetches with the real Bearer token, returns only the JSON
   body (no headers / token leak).
```

### Scope model

- `plugin.json` gains `api_scopes: ["read:storage", "read:system-info", …]` (separate from the existing backend `required_permissions`).
- A **fixed, Core-maintained catalog** maps each scope → concrete allowed method + path pattern:
  ```
  read:system-info  → GET /api/system/info
  read:storage      → GET /api/files/storage*, GET /api/system/storage*
  read:power        → GET /api/power/*
  …  (start small, curate additively; NO write:* scopes on sensitive Core routes in v1)
  ```
  Plugins can never invent a scope that opens `/api/users` or `/api/auth` — those appear in no catalog entry.
- **Admin grant at install:** declared scopes are shown in the install dialog ("This plugin wants: read storage info") and stored as granted/denied on the `InstalledPlugin` row. Ungranted scopes are blocked even if declared.
- **Audit:** `scope_denied` calls are logged (rate-limited) → visible when a plugin reaches beyond its grant.

Deliberately excluded in v1: write Core scopes, wildcard scopes, plugin-to-plugin calls. Plugins needing Core writes encapsulate them behind their **own** backend route (isolated under Track B).

## Host Integration

- New `PluginSandboxHost` (`client/src/components/plugins/`) wraps iframe + bridge. `PluginPage` keeps the chrome (title / `PluginBadge` / error states) and renders `<PluginSandboxHost pluginName … user … />` instead of `<PluginComponent>`.
- `client/src/lib/pluginLoader.ts` (the `import()` path) and `client/src/lib/pluginSDK.ts` (`initPluginSDK` in the main context) are **removed** — the main context no longer exposes `window.BaluHost`, directly closing the audit gap.
- iframe height driven by the `resize` event; loading / error / timeout states owned by the host.

## Migration of the 3 Bundled Plugins (part of this track)

`optical_drive`, `storage_analytics`, `tapo_smart_plug`:

- Switch the build target to externals / runtime ABI.
- Add `api_scopes` + `min_runtime_abi` to each `plugin.json`.
- Re-point any calls that hit Core endpoints onto their own routes or declared scopes. JSX stays largely as-is.
- They double as the **reference implementation** and an end-to-end smoke test of the whole chain.

## Backend Changes (small)

- New route `GET /api/plugins/{name}/ui/host.html` (sandbox bootstrap) + permissive CORS on the `ui/` asset routes.
- Route serving the versioned `plugin-runtime.js`.
- `plugin.json` schema + `PluginManifest` model gain `api_scopes` / `min_runtime_abi`; `InstalledPlugin` gains granted scopes (Alembic migration, chained onto the real `alembic heads` — see `project_alembic_migration_head_pitfall`).
- Scope catalog as a Core constant; `scope_denied` audit logging.

## Error Handling

- Bridge RPC timeout (30 s) → reject with `{code:'timeout'}`; surfaced in-plugin via the rejected promise.
- Unknown channel/method → `{code:'unknown_channel'}`.
- `scope_denied` → returned to the plugin and audit-logged.
- Runtime ABI mismatch (`min_runtime_abi` > runtime) → host shows a clean "plugin needs a newer BaluHost" message, does not load `bundle.js`.
- iframe load failure / bundle parse error → host error state (mirrors today's `PluginPage` error UI).

## Testing

- **Bridge RPC unit tests:** envelope handling, timeout, unknown channel → reject.
- **Policy tests:** own route allowed; Core route without scope denied; `/api/users` never reachable; `..` / non-`/api/` denied; granted-but-not-declared and declared-but-not-granted both denied.
- **Vitest** for `PluginSandboxHost`: handshake, resize, unmount rejects pending RPCs.
- **E2E (Playwright):** a test plugin loads in the iframe, makes one allowed + one denied call, observes the expected outcome; asserts the main context exposes no `window.BaluHost`.
- **Migration smoke:** the 3 bundled plugins load and function under the new model.

## Implementation Phases (each shippable)

1. **Bridge core + envelope** — `PluginSandboxHost` + in-iframe runtime skeleton, handshake, `toast`/`navigate`/`resize` channels. A trivial test plugin renders in the sandbox.
2. **API channel + policy** — own-routes-only first, then the scope catalog + manifest `api_scopes` + `InstalledPlugin` grant + install-dialog UI + audit.
3. **Runtime UI lib + theme CSS** — ship React + UI components + Tailwind theme into the iframe; `storage` channel.
4. **Migrate the 3 bundled plugins** + remove `pluginLoader.ts` / main-context `pluginSDK.ts`.
5. **E2E + docs** — Playwright coverage, plugin-author migration guide, `min_runtime_abi`/ABI versioning.

## Open Questions / Future Hardening

- Separate-origin iframe (real domain/port) as defense-in-depth over the opaque origin.
- Per-plugin Content-Security-Policy on the sandbox document (tighten `connect-src`/`script-src` inside the frame).
- Whether `storage` persists server-side (per-plugin table) or client-side (bounded prefix) — decided in Phase 3.
