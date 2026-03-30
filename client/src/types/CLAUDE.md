# Types

TypeScript type definitions and ambient declarations.

## Files

| File | Purpose |
|---|---|
| `auth.ts` | `User` interface (`id`, `username`, `email?`, `role`) and `AuthState` interface |
| `vcl.ts` | File versioning (VCL) types |
| `electron.d.ts` | Ambient declarations for Electron IPC bridge (`window.electronAPI`) |
| `plugin-sdk.d.ts` | Ambient declarations for plugin SDK globals |

## Conventions

- Shared domain types used across multiple modules go here
- Component-specific types (props interfaces) stay in the component file
- API response types stay in the `api/` module that uses them
- Use `interface` for object shapes, `type` for unions/intersections
- Ambient declarations (`*.d.ts`) for globals injected by build tools (Vite define, Electron preload)

## Build-time Globals

Declared via `vite-env.d.ts` and ambient files:
- `__DEVICE_MODE__`: `'desktop' | 'pi'` — build-time device target (Vite define)
- `import.meta.env.DEV` / `import.meta.env.VITE_API_BASE_URL` — Vite environment variables
