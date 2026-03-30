# Pages

Top-level route components. Each page is lazy-loaded in `App.tsx` via `lazyWithRetry()` (auto-retries on chunk load failure).

## Device Modes

Pages are conditionally included based on `__DEVICE_MODE__` build flag:
- **Desktop (NAS)**: Full feature set — all pages loaded
- **Pi (BaluPi)**: Only `Login`, `Dashboard`, `SystemMonitor`, `PiDashboard` — everything else tree-shaken out

## Pages

| Page | Route | Auth | Description |
|---|---|---|---|
| `Login.tsx` | `/login` | No | Login/register with server profile selection |
| `Dashboard.tsx` | `/` | Yes | Main dashboard with widgets, plugin panels |
| `FileManager.tsx` | `/files` | Yes | File browser with upload, preview, sharing |
| `SystemMonitor.tsx` | `/system` | Yes | CPU, memory, network, disk charts |
| `RaidManagement.tsx` | `/raid` | Admin | RAID array management, disk status |
| `PowerManagement.tsx` | `/power` | Admin | CPU frequency profiles, power demands |
| `FanControl.tsx` | `/fans` | Admin | Fan curves, schedules, temperature monitoring |
| `SleepMode.tsx` | `/sleep` | Admin | Sleep mode configuration, idle detection |
| `UserManagement.tsx` | `/users` | Admin | User CRUD, roles, 2FA management |
| `SettingsPage.tsx` | `/settings` | Yes | User settings (theme, language, byte units, sync, backup) |
| `SharesPage.tsx` | `/shares` | Yes | File share management |
| `VpnPage.tsx` | `/vpn` | Admin | VPN client management |
| `Logging.tsx` | `/logging` | Admin | Audit log viewer |
| `AdminDatabase.tsx` | `/admin-db` | Admin | Database table inspector |
| `AdminHealth.tsx` | `/admin/health` | Admin | Service health dashboard |
| `SchedulerDashboard.tsx` | `/schedulers` | Admin | Background scheduler status and history |
| `DevicesPage.tsx` | `/devices` | Yes | Desktop/mobile device management |
| `MobileDevicesPage.tsx` | `/mobile` | Admin | Mobile device registration |
| `PluginsPage.tsx` | `/plugins` | Admin | Plugin install, toggle, configure |
| `SmartDevicesPage.tsx` | `/smart-devices` | Admin | Smart device (Tapo) management |
| `PiholePage.tsx` | `/pihole` | Admin | Pi-hole DNS management |
| `CloudImportPage.tsx` | `/cloud` | Yes | Cloud import (Google Drive, Dropbox, etc.) |
| `BackupPage.tsx` | `/backups` | Admin | Backup creation and restore |
| `UpdatePage.tsx` | `/updates` | Admin | Self-hosted update management |
| `NotificationsArchivePage.tsx` | `/notifications` | Yes | Notification history |
| `SystemControlPage.tsx` | `/system-control` | Admin | System shutdown, restart, SMART, energy |
| `UserManualPage.tsx` | `/manual` | Yes | User manual article viewer |
| `PiDashboard.tsx` | `/pi` | Yes | BaluPi-specific compact dashboard (Pi build only) |

## Conventions

- Pages compose feature components from `components/` — minimal logic in page files
- Admin pages use `Depends(get_current_admin)` on backend — frontend checks `isAdmin` for nav visibility but backend enforces
- Use `useTranslation(namespace)` for all user-facing strings
- Lazy loading: all pages imported via `lazyWithRetry()` in `App.tsx` wrapped in `<Suspense>`
