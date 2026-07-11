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
- `Pill.tsx` — Inline status/tag pill chip
- `index.ts` — Barrel re-export for all ui/ primitives

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
- Settings: `AppearanceSettings.tsx`, `LanguageSettings.tsx`, `ByteUnitSettings.tsx`, `BackupSettings.tsx`
- `AdminDataTable.tsx` — Generic sortable/filterable table for admin views
- `DesktopPairingDialog.tsx` — Desktop client pairing QR/PIN dialog
- `EnergyMonitor.tsx` — Energy consumption monitoring widget
- `ImpersonationBanner.tsx` — Banner shown when admin is impersonating a user
- `LocalOnlyAction.tsx` — Wrapper that gates actions to local-network-only access
- `UserMenu.tsx` — User dropdown menu (avatar, logout, settings link)
- `UserMenuQuickSettings.tsx` — Quick-settings panel within the user menu

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
| `power/` | Power profile management — `PowerManagement` page composes `PowerStatusCards`, `PermissionStatusCard`, `AutoScalingSection` (extracted F2/#301); `SleepConfigPanel` composes ./sleep-config/* (8 section cards + SleepFormControls), form state in useSleepConfigForm/useFritzBoxForm (extracted F2) |
| `raid/` | RAID status, disk details |
| `rate-limits/` | Rate limit configuration UI |
| `RemoteServers/` | Remote server profile management |
| `samba/` | Samba/SMB share management |
| `scheduler/` | Scheduler status and history |
| `services/` | Background service status cards |
| `settings/` | Settings page sections |
| `shares/` | Share management — `SharesPage` composes `SharesStatCards`, `SharesTabBar`, `SharesToolbar`, `MySharesTable`, `SharedWithMeTable`, `CloudExportsTable` (+ `PermissionBadges`/`FileNameCell`/`CloudStatusBadge` primitives), extracted F2/#301-style |
| `smart-devices/` | Smart device status and control |
| `ssd-cache/` | SSD file cache management |
| `system-monitor/` | System monitor detail views |
| `updates/` | Self-update UI |
| `user-management/` | User CRUD, 2FA management |
| `setup/` | Setup wizard step components |
| `vcl/` | File versioning UI |
| `webdav/` | WebDAV server control |
| `balupi/` | BaluPi-specific compact UI components |
| `nfs/` | NFS share management components |
| `quickSettings/` | Quick-settings panel components (user menu) |
| `status-bar-config/` | Status bar strip configuration editor |
| `topbar/` | Topbar/header components including status strip |

## Conventions

- Functional components only, with TypeScript interfaces for props
- Tailwind CSS for all styling (via CSS variables from ThemeContext for theming)
- Icons: `lucide-react` (import individual icons, not the whole library)
- Error display: `toast.error()` from `react-hot-toast` via `handleApiError()`
- i18n: `useTranslation()` hook with namespace (e.g., `useTranslation('fileManager')`)
- Loading states: `Spinner` component or conditional rendering
- Feature gating: check `FEATURES.*` or `isDesktop` from `lib/features.ts` for device-conditional rendering
