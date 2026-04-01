# Components

React functional components. Split into top-level shared components and feature-specific subdirectories.

## Structure

### `ui/` — Primitive UI Components
Reusable, generic building blocks. No business logic, no API calls.
- `Button.tsx`, `Input.tsx`, `Select.tsx` — Form elements
- `Card.tsx`, `Badge.tsx`, `StatCard.tsx` — Display elements
- `Modal.tsx`, `ConfirmDialog.tsx`, `IdleWarningDialog.tsx` — Overlays
- `Spinner.tsx`, `ProgressBar.tsx`, `EmptyState.tsx` — Feedback
- `Tabs.tsx`, `SortableHeader.tsx` — Navigation/tables
- `ByteSizeInput.tsx` — Byte-aware number input
- `AdminBadge.tsx`, `PluginBadge.tsx`, `DeveloperBadge.tsx` — Role indicators

### Top-level Components (shared across pages)
- `Layout.tsx` — Main layout with sidebar navigation, header, power menu, notification center
- `ErrorBoundary.tsx` — React error boundary with fallback UI
- `UploadProgressBar.tsx` — Global file upload progress
- `NotificationCenter.tsx` — Real-time notification dropdown (WebSocket)
- `PowerMenu.tsx` / `PowerStatusWidget.tsx` — System power controls
- `PluginPage.tsx` — Dynamic plugin page renderer
- `RaidSetupWizard.tsx` / `MockDiskWizard.tsx` — RAID setup wizards
- `VpnManagement.tsx` — VPN client management
- `ShareFileModal.tsx`, `CreateFileShareModal.tsx`, `EditFileShareModal.tsx` — File sharing modals
- Settings: `AppearanceSettings.tsx`, `LanguageSettings.tsx`, `ByteUnitSettings.tsx`, `BackupSettings.tsx`, `SyncSettings.tsx`

### Feature Subdirectories
| Directory | Feature |
|---|---|
| `admin/` | Admin-specific panels and tools |
| `benchmark/` | Disk benchmark UI |
| `cloud/` | Cloud import/export components |
| `dashboard/` | Dashboard widgets and `panels/` for plugin panels |
| `device-management/` | Device management (desktop, mobile) |
| `env-config/` | Runtime environment variable editor |
| `fan-control/` | Fan curves, schedules, profiles |
| `file-manager/` | File browser, context menus, preview |
| `firebase/` | Firebase push notification config |
| `manual/` | User manual article viewer |
| `monitoring/` | System monitoring charts and cards |
| `pihole/` | Pi-hole DNS dashboard, `ad-discovery/` |
| `plugins/` | Plugin management UI |
| `power/` | Power profile management |
| `raid/` | RAID status, disk details |
| `rate-limits/` | Rate limit configuration UI |
| `RemoteServers/` | Remote server profile management |
| `samba/` | Samba/SMB share management |
| `scheduler/` | Scheduler status and history |
| `services/` | Background service status cards |
| `settings/` | Settings page sections |
| `smart-devices/` | Smart device status and control |
| `ssd-cache/` | SSD file cache management |
| `sync-settings/` | Desktop sync configuration |
| `system-monitor/` | System monitor detail views |
| `updates/` | Self-update UI |
| `user-management/` | User CRUD, 2FA management |
| `setup/` | Setup wizard step components |
| `vcl/` | File versioning UI |
| `webdav/` | WebDAV server control |

## Conventions

- Functional components only, with TypeScript interfaces for props
- Tailwind CSS for all styling (via CSS variables from ThemeContext for theming)
- Icons: `lucide-react` (import individual icons, not the whole library)
- Error display: `toast.error()` from `react-hot-toast` via `handleApiError()`
- i18n: `useTranslation()` hook with namespace (e.g., `useTranslation('fileManager')`)
- Loading states: `Spinner` component or conditional rendering
- Feature gating: check `FEATURES.*` or `isDesktop` from `lib/features.ts` for device-conditional rendering
