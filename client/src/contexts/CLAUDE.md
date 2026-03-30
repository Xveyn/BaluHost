# Contexts

React Context providers for global state. Wrapped around the app in `App.tsx`.

## Contexts

| File | Purpose | Key values |
|---|---|---|
| `AuthContext.tsx` | Authentication state. Validates stored JWT on mount via `/api/auth/me`. Listens for `auth:expired` events (fired by axios 401 interceptor) | `user`, `token`, `login()`, `logout()`, `isAdmin`, `loading` |
| `ThemeContext.tsx` | Theme management. 6 themes: `light`, `dark`, `ocean`, `forest`, `sunset`, `midnight`. Applies CSS variables to `:root` | `theme`, `setTheme()` |
| `UploadContext.tsx` | File upload state management (progress, queue, cancellation) | Upload queue, progress tracking |
| `NotificationContext.tsx` | In-app notification state (WebSocket-driven) | Notification list, unread count |
| `PluginContext.tsx` | Plugin system state (loaded plugins, nav items, UI manifests) | `plugins`, plugin metadata |
| `VersionContext.tsx` | App version info from backend | `version`, `useFormattedVersion()` |

## Patterns

- All contexts use `createContext<T | null>(null)` with a custom `useX()` hook that throws if used outside the provider
- Token stored in `localStorage` under key `token`
- Theme stored in `localStorage` under key `baluhost-theme`
- Auth flow: token in localStorage -> validate on mount -> set user state or clear
- Provider nesting order in `App.tsx`: `AuthProvider` > `VersionProvider` > `PluginProvider` > `NotificationProvider` > `UploadProvider`
