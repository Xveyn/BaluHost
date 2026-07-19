# Components

React functional components. Split into top-level shared components and feature-specific subdirectories.

## Structure

### `ui/` — Primitive UI Components
Reusable, generic building blocks. No business logic, no API calls.
- `Button.tsx`, `Input.tsx`, `Select.tsx` — Form elements
- `Card.tsx`, `Badge.tsx`, `StatCard.tsx` — Display elements
- `Modal.tsx`, `ConfirmDialog.tsx`, `IdleWarningDialog.tsx` — Overlays
- `Spinner.tsx`, `ProgressBar.tsx`, `EmptyState.tsx`, `LoadingFallback.tsx` — Feedback (`LoadingFallback` is the route-Suspense fallback, `size: 'full' | 'inline'` — `'full'` for top-level fallbacks that render before `Layout` mounts, `'inline'` for the boundary inside `Layout`'s content area, extracted F2/#301)
- `Tabs.tsx`, `SortableHeader.tsx` — Navigation/tables
- `ByteSizeInput.tsx` — Byte-aware number input
- `AdminBadge.tsx`, `PluginBadge.tsx`, `DeveloperBadge.tsx` — Role indicators
- `Pill.tsx` — Inline status/tag pill chip
- `index.ts` — Barrel re-export for all ui/ primitives

### Top-level Components (shared across pages)
- `Layout.tsx` — Thin orchestrator over `layout/*` (sidebar navigation, header, power overlay); mounted once via the `AppLayout` layout route (F2/#301)
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
| `dashboard/` | Dashboard widgets and `panels/` for plugin panels — `QuickStatCard`/`statIcons` (quick-stat tile + shared icon set), `SmartHealthPanel` composing `SmartDeviceCard` per SMART device, `RaidSummaryCard`, `SystemHealthCard` (health-checklist card), `computeSmartDeviceUsage` pure helper (SMART device used-bytes/percent derivation) — extracted from Dashboard.tsx (F2/#301) |
| `device-management/` | Device management (desktop, mobile) |
| `env-config/` | Runtime environment variable editor |
| `fan-control/` | Fan curves, schedules, profiles — `FanDetails` composes `fan-details/*` (`FanPresetProfileButtons`, `FanCurveGraphControls`, `FanCurveTableEditor`, `FanStatsGrid`) + pure `fanCurveValidation`; state/handlers in `hooks/useFanCurveEditor`. `FanCurveChart` composes `fan-curve-chart/*` (`FanCurveTooltip`, `FanChartLegend`, `FanChartHint`) + pure `fanCurveGeometry`; drag/click/touch interaction in `hooks/useFanCurveInteraction` (extracted F2/#301) |
| `file-manager/` | File browser, context menus, preview |
| `firebase/` | Firebase push notification config |
| `layout/` | App shell — `AppLayout` (layout route: `<Layout><Suspense><Outlet/></Suspense></Layout>`), `DesktopSidebar`/`MobileSidebar` (composing `SidebarBrand`+`SidebarNav`), `LayoutHeader`, `PendingPowerOverlay`, `layoutNavConfig` (icons + `buildNavItems`); nav filtering in `hooks/useLayoutNav`, shutdown/restart in `hooks/usePowerActions` (extracted F2/#301) |
| `manual/` | User manual article viewer — `ApiReferenceTab` composes `api-reference/*` (`EndpointCard`, `ApiViewToggle`, `ApiBaseUrlCard`, `ApiSearchBar`, `ApiCategoryTabs`, `ApiSchemaError`, `ApiLoadingSkeleton`, `ApiSectionList`) + pure `lib/apiRateLimitMatch`; state/fetch in `hooks/useApiReference` (extracted F2/#301) |
| `mobile-devices/` | Mobile device registration — `MobileDevicesPage` composes `mobile-devices/*`: `RegisterDeviceCard`, `MobileDevicesList`/`MobileDeviceCard`, `NotificationStatus`, `QrCodeDialog` (→ `NewTokenQrView` / `ExistingDeviceInfoView`) + `mobileDeviceDates` helper; state/handlers in `hooks/useMobileRegistration` (extracted F2/#301). **Note:** `pages/MobileDevicesPage.tsx` is currently not routed or mounted anywhere — only comments reference it. See `pages/CLAUDE.md` → "Unrouted page components" |
| `monitoring/` | System monitoring charts and cards |
| `pihole/` | Pi-hole DNS dashboard, `ad-discovery/` |
| `plugins/` | Plugin management UI — `plugin-management/` holds the `PluginsPage` decomposition: `PluginTabNav`, `PluginList`/`PluginListCard`, `PluginDetailsSidebar` (composing `PluginDetailsCard`/`PluginPermissionsCard`/`PluginDashboardPanelCard`/`PluginActionsCard`), `PermissionGrantModal`, `ScopeGrantModal`, `getCategoryColor` helper — re-exported via `plugin-management/index.ts`; state/actions in `hooks/usePluginManagement.ts` (extracted F2/#301) |
| `power/` | Power profile management — `PowerManagement` page composes `PowerStatusCards`, `PermissionStatusCard`, `AutoScalingSection` (extracted F2/#301); `SleepConfigPanel` composes ./sleep-config/* (8 section cards + SleepFormControls), form state in useSleepConfigForm/useFritzBoxForm (extracted F2) |
| `raid/` | RAID status, disk details |
| `raid-setup/` | RAID creation wizard — `RaidSetupWizard` composes `raid-setup/*`: `RaidWizardStepIndicator`, `RaidDiskSelectionStep`, `RaidLevelSelectionStep`, `RaidConfirmationStep` + `raidLevels` data + pure `raidWizardHelpers` (`calculateArrayCapacity`/`isValidArrayName`); state/navigation/submit in `hooks/useRaidSetupWizard` (extracted F2/#301) |
| `rate-limits/` | Rate limit configuration UI |
| `RemoteServers/` | Remote server profile management |
| `samba/` | Samba/SMB share management |
| `scheduler/` | Scheduler status and history |
| `services/` | Background service status cards |
| `settings/` | Settings page sections |
| `shares/` | Share management — `SharesPage` composes `SharesStatCards`, `SharesTabBar`, `SharesToolbar`, `MySharesTable`, `SharedWithMeTable`, `CloudExportsTable` (+ `PermissionBadges`/`FileNameCell`/`CloudStatusBadge` primitives), extracted F2/#301-style |
| `smart-devices/` | Smart device status and control |
| `ssd-cache/` | SSD file cache management — `SsdFileCacheTab` composes `file-cache/*`: `CacheViewTabs`, `CacheArraySelector`, `CacheStatsGrid`, `CacheHealthCard`, `CacheConfigCard`, `CacheActionsCard`, `CacheEntriesTable` (+ `cacheUsageBarColor` helper), re-exported via `file-cache/index.ts`; state/effects/handlers in `hooks/useSsdFileCache.ts` (extracted F2/#301) |
| `system-monitor/` | System monitor detail views — `PowerTab` composes `power-tab/*`: `PowerSummaryCards`, `PowerDeviceCard`, `EnergyPriceEditor`, `ChartDeviceTabs`, `ChartModePeriodControls`, `CustomRangePicker`, `EnergyChartSummary`, `EnergyChart` (+ `CumulativeEnergyChart`/`InstantPowerChart`), `PowerStates`, and the `parseDevicePower` pure helper — extracted F2/#301 |
| `updates/` | Self-update UI |
| `user-management/` | User CRUD, 2FA management |
| `setup/` | Setup wizard step components |
| `vcl/` | File versioning UI — `VCLSettings` (admin) composes `vcl-settings/*`: `VclMessageBanners`, `VclStorageInfoCard`, `VclStatsGrid`, `VclStorageDetailsCard`, `VclMaintenanceCard`, `VclReconciliationCard`, `VclUserQuotasTable`, `VclEditUserModal` (+ `usageBarColor` helper), all re-exported via `vcl-settings/index.ts`; state/handlers in `hooks/useVclSettings.ts` (extracted F2/#301) |
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
