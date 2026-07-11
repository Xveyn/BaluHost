# MobileDevicesPage.tsx Decomposition — Design (F2 / #301)

**Date:** 2026-07-12
**Finding:** F2 (components > 500 lines), umbrella issue #301.
**Target:** `client/src/pages/MobileDevicesPage.tsx` — currently **613 lines**.

## Goal

Behavior-preserving decomposition of `MobileDevicesPage.tsx` (the admin mobile
device registration page: generate-token card, device list, QR dialog) into one
data/state hook, a pure date/expiry helper module, and a directory of
presentational components under a new `components/mobile-devices/`.

**Non-goals:** no change to API calls, endpoints, query keys, polling
(`useMobileDevices` 10s), i18n keys, copy, Tailwind styling, `confirm(...)`
wording, `localStorage` persistence, the `qr_code` base64-prefix detection, or
any computed value. The page keeps its path (`pages/MobileDevicesPage.tsx`,
**default export** `MobileDevicesPage`) and route (`/mobile`, admin) so `App.tsx`
lazy-loading and consumers are untouched.

**i18n note:** this file is the inverse of SsdCache/VCL — copy is
**predominantly hard-coded German**, with only a handful of `t('mobile.*')` /
`t('time.*')` calls in the `common` namespace. Every string stays **verbatim**;
the i18n migration is scope creep tracked in issue #406 (which now lists this
page, related to #166).

## Constraints

- Every extracted value is **byte-identical** in behavior: same
  `generateMobileToken(includeVpn, deviceName.trim(), tokenValidityDays,
  vpnType)` call, same `localStorage.setItem('lastMobileToken', …)` payload +
  try/catch, same `deleteMobileDevice` + `refetchDevices()` on both success and
  error paths, same `confirm(...)` strings, same close-reset (incl.
  `if (qrData) void refetchDevices()`), same `data:${… .startsWith('iVBOR') ?
  'image/png' : 'image/svg+xml'};base64,${…}` src, same
  `toLocaleString('de-DE')` formatting.
- Extracted components are **presentational**: props in, callbacks in, no data
  fetching. The one exception is `NotificationStatus`, which owns its own
  `useQuery` today and keeps it (moved verbatim) — it is a self-contained leaf
  that fetches one device's last notification.
- The expiry computation currently duplicated **3×** (device-card line 332–348,
  existing-device-view color 500–508, existing-device-view badge 512–520) is
  deduped into one pure helper. Output must be identical at every call site.
- Tests are T7-conform: assert on role/text/title, never Tailwind classes;
  fixtures are complete objects of the real types (`MobileDevice`,
  `MobileRegistrationToken`). **German-locale gotcha:** never assert on
  `toLocaleString`-separator-formatted numbers/dates; assert on plain values or
  labels.

## Current inline blocks (what moves)

| Block | Current lines | Destination |
|---|---|---|
| 9 `useState` + reads (`useMobileDevices`, vpnTypes `useQuery`) + `useConfirmDialog` + `useTranslation('common')` + handlers (`handleGenerateToken`, `handleDeleteDevice`, `handleShowDeviceQr`, close-reset) | 13–93, 380–389 | `hooks/useMobileRegistration.ts` |
| `formatDate` (73–77), `getTimeAgo` (79–88), the 3× expiry ternary, `NotificationStatus` inline timeAgo (588–594) | scattered | `mobile-devices/mobileDeviceDates.ts` (pure) |
| Generate-token card (name, validity slider, auto-reminder note, VPN checkbox + warnings + type selector, generate button) | 104–237 | `mobile-devices/RegisterDeviceCard.tsx` |
| Devices-list card (header + refresh + loading/empty/list) | 240–369 | `mobile-devices/MobileDevicesList.tsx` |
| One device card (info grid + expiry + delete btn) | 269–365 | `mobile-devices/MobileDeviceCard.tsx` |
| `NotificationStatus` sub-component | 571–612 | `mobile-devices/NotificationStatus.tsx` |
| QR dialog overlay + header + close button + branch switch | 372–394, 559–562 | `mobile-devices/QrCodeDialog.tsx` |
| New-token QR view | 396–464 | `mobile-devices/NewTokenQrView.tsx` |
| Existing-device info view | 465–559 | `mobile-devices/ExistingDeviceInfoView.tsx` |

## New units & interfaces

### `mobile-devices/mobileDeviceDates.ts` (pure)

```ts
import type { TFunction } from 'i18next';

export function formatMobileDate(dateString: string | null): string;
// null → 'Nie'; else new Date(dateString).toLocaleString('de-DE')

export interface MobileExpiry { daysLeft: number; isExpired: boolean; isExpiringSoon: boolean; }
export function mobileExpiry(expiresAt: string): MobileExpiry;
// daysLeft = Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 86_400_000)
// isExpired = daysLeft <= 0; isExpiringSoon = daysLeft <= 7

export function mobileTimeAgo(dateString: string | null, t: TFunction): string;
// ports getTimeAgo verbatim: null → t('time.never','Nie'); <60s t('time.justNow');
// <3600 t('time.minutesAgo',{count}); <86400 t('time.hoursAgo',{count});
// else t('time.daysAgo',{count})

export function notificationTimeAgo(dateString: string): string;
// ports NotificationStatus's inline German timeAgo verbatim:
// <60 'Gerade eben'; <3600 `Vor ${n} Min`; <86400 `Vor ${n} Std`; else `Vor ${n} Tagen`
```

`mobileExpiry` replaces all three inline copies. The device-card badge uses
`{daysLeft}d`; the existing-device badge uses `{daysLeft} Tage` / `Aktiv` — those
label differences stay in their respective components (the helper returns only
the booleans + `daysLeft`).

### `hooks/useMobileRegistration.ts`

```ts
import type { MobileRegistrationToken, MobileDevice } from '../api/mobile';
import type { ReactNode } from 'react';

export interface UseMobileRegistrationResult {
  // reads
  devices: MobileDevice[];
  loading: boolean;
  isFetching: boolean;
  availableVpnTypes: string[];
  // form state
  deviceName: string;
  setDeviceName: (v: string) => void;
  tokenValidityDays: number;
  setTokenValidityDays: (v: number) => void;
  includeVpn: boolean;
  setIncludeVpn: (v: boolean) => void;
  vpnType: string;
  setVpnType: (v: string) => void;
  generating: boolean;
  // dialog state
  showQrDialog: boolean;
  qrData: MobileRegistrationToken | null;
  selectedDevice: MobileDevice | null;
  showToken: boolean;
  toggleShowToken: () => void;
  // handlers
  handleGenerateToken: () => Promise<void>;
  handleDeleteDevice: (deviceId: string, deviceName: string) => Promise<void>;
  handleShowDeviceQr: (device: MobileDevice) => void;
  refetchDevices: () => void;
  closeQrDialog: () => void;
  // confirm dialog element to render
  dialog: ReactNode;
}

export function useMobileRegistration(): UseMobileRegistrationResult;
```

Body ports lines 13–93 + the close-reset (380–389) verbatim: the 9 `useState`,
`useMobileDevices()`, the vpnTypes `useQuery`, `useConfirmDialog()` (uses
`confirm` internally, exposes `dialog`), `useTranslation('common')` (needed by
`handleGenerateToken`'s error toast + `mobileTimeAgo`), and every handler. `t` is
**not** exposed; components that need relative-time call `mobileTimeAgo(date, t)`
where the page passes `t` — see note below. `closeQrDialog` bundles the 8 resets
+ `if (qrData) void refetchDevices()`. `toggleShowToken` = `setShowToken(s => !s)`.

**`t` handoff:** `mobileTimeAgo` needs `t`. Rather than thread `t` through props,
`MobileDeviceCard` calls `useTranslation('common')` itself for the single
`mobileTimeAgo` call (the page already treats `common` as its namespace; a
presentational component reading `t` for display text is the established codebase
pattern — see `VclStorageInfoCard`). No data fetching is introduced. The hook
still owns `t` for the generate-error toast.

### Presentational components (`components/mobile-devices/`)

- **`RegisterDeviceCard.tsx`** — `{ deviceName: string; onDeviceNameChange:
  (v: string) => void; tokenValidityDays: number; onValidityChange: (v: number)
  => void; includeVpn: boolean; onIncludeVpnChange: (v: boolean) => void;
  vpnType: string; onVpnTypeChange: (v: string) => void; availableVpnTypes:
  string[]; generating: boolean; onGenerate: () => void }`. The whole
  generate-token card (104–237): name input, validity slider (incl. the inline
  `linear-gradient` style + `((tokenValidityDays - 30) / 150) * 100` math),
  auto-reminder box, VPN checkbox, both VPN warning branches, the VPN-type
  selector (`availableVpnTypes.length > 1`) with its `[{value:'auto',…}, …]`
  array + per-type description text, and the generate button (spinner vs
  `QR-Code generieren`, `disabled={generating || !deviceName.trim()}`).
- **`MobileDevicesList.tsx`** — `{ devices: MobileDevice[]; loading: boolean;
  isFetching: boolean; isAdmin: boolean; onRefresh: () => void; onShowQr:
  (device: MobileDevice) => void; onDelete: (id: string, name: string) => void }`.
  The list card (240–369): header + `Registrierte Geräte ({devices.length})` +
  refresh button (`title="Aktualisieren"`), loading state, empty state, and
  `devices.map(...)` → `MobileDeviceCard`.
- **`MobileDeviceCard.tsx`** — `{ device: MobileDevice; isAdmin: boolean;
  onShowQr: (device: MobileDevice) => void; onDelete: (id: string, name: string)
  => void }`. One device card (269–365). Calls `useTranslation('common')` for
  `mobileTimeAgo`. Uses `formatMobileDate`, `mobileExpiry`. Contains
  `<NotificationStatus deviceId={device.id} />`. Delete button keeps
  `e.stopPropagation()`.
- **`NotificationStatus.tsx`** — `{ deviceId: string }`. Moved verbatim incl. its
  own `useQuery(queryKeys.mobile.deviceNotifications(deviceId), …)`; uses
  `notificationTimeAgo`; hard-coded German labels verbatim; returns `null` when
  no notification.
- **`QrCodeDialog.tsx`** — `{ qrData: MobileRegistrationToken | null;
  selectedDevice: MobileDevice | null; isAdmin: boolean; showToken: boolean;
  onToggleToken: () => void; onClose: () => void }`. The overlay shell + header
  (`qrData ? 'QR-Code für Mobile App' : \`QR-Code: ${selectedDevice?.device_name}\``)
  + close button (wired to `onClose`), then renders `<NewTokenQrView>` when
  `qrData`, else `<ExistingDeviceInfoView>` when `selectedDevice`, else `null`.
  The `showQrDialog && (qrData || selectedDevice)` mount guard stays in the
  orchestrator.
- **`NewTokenQrView.tsx`** — `{ qrData: MobileRegistrationToken; showToken:
  boolean; onToggleToken: () => void }`. The new-token view (396–464): QR `<img>`
  with the base64-prefix logic, token show/copy (`navigator.clipboard.writeText`
  + `toast.success('Token kopiert')`), the `✓ …` lines with
  `device_token_validity_days`, VPN-included / fallback notes, reminder box, and
  the `Token läuft ab:` `toLocaleString('de-DE')` line.
- **`ExistingDeviceInfoView.tsx`** — `{ device: MobileDevice; isAdmin: boolean }`.
  The existing-device info view (465–559): warning banner, device-info block
  (uses `formatMobileDate` + `mobileExpiry` for the color + badge), the
  `window.location.origin` / Device ID / Status connection block, and the
  "So registrierst du das Gerät neu:" ordered list.

### `mobile-devices/index.ts`

Barrel exporting all seven components + the four helpers.

### `MobileDevicesPage.tsx` (after)

Calls `useMobileRegistration()` and `useAuth()` (for `isAdmin`, a page-level
concern passed to `MobileDevicesList` + `QrCodeDialog`). Keeps the header (98–101)
inline. Composes `RegisterDeviceCard` (form state + `onGenerate`),
`MobileDevicesList` (`onShowQr={handleShowDeviceQr}`, `onDelete={handleDeleteDevice}`,
`onRefresh={refetchDevices}`), `{showQrDialog && (qrData || selectedDevice) &&
<QrCodeDialog … onToggleToken={toggleShowToken} onClose={closeQrDialog} />}`, and
`{dialog}`. Target: **~90–110 lines** (from 613).

## Testing

Broad + integration (Vitest, T7-conform):

- **`mobileDeviceDates`** — `formatMobileDate(null) → 'Nie'`;
  `formatMobileDate('…')` returns a non-empty string (no separator assertion);
  `mobileExpiry` — future date > 7d → `{isExpired:false, isExpiringSoon:false}`,
  date 3 days out → `isExpiringSoon && !isExpired`, past date → `isExpired`;
  `mobileTimeAgo(null, t) → 'time.never'` and `<60s → 'time.justNow'` with a
  `t = (k) => k` stub; `notificationTimeAgo` — <60s → `'Gerade eben'`, ~2min →
  `'Vor 2 Min'`. Use fixed epoch strings computed against a stubbed clock; **do
  not** rely on wall-clock `Date.now()` in assertions (compute inputs relative to
  a captured `now`).
- **`useMobileRegistration`** — `renderHook`: `handleGenerateToken` with empty
  `deviceName` toasts and does **not** call `generateMobileToken`;
  `handleGenerateToken` with a name calls `generateMobileToken(includeVpn,
  'Name', tokenValidityDays, vpnType)`, sets `qrData`, writes `lastMobileToken`
  to `localStorage`, opens the dialog; `handleDeleteDevice` with `confirm`
  returning `false` does **not** call `deleteMobileDevice`; `closeQrDialog`
  resets `deviceName`/`includeVpn`/`vpnType`/`showToken` and (when `qrData` was
  set) calls `refetchDevices`. Mock `../api/mobile`, `../hooks/useMobileDevices`,
  `../hooks/useConfirmDialog`, `react-hot-toast`, and `localStorage`.
- **Component renders** — `RegisterDeviceCard` (name change fires
  `onDeviceNameChange`; generate button disabled when name blank; VPN-type
  selector appears only when `availableVpnTypes.length > 1`; clicking a type
  fires `onVpnTypeChange`); `MobileDevicesList` (loading → spinner text; empty →
  "Keine Geräte registriert"; one row per device; refresh fires `onRefresh`;
  admin username shown only when `isAdmin`); `MobileDeviceCard` (device name +
  `Aktiv`/`Inaktiv`; expired badge for a past `expires_at`; delete fires
  `onDelete` with id+name and does not trigger `onShowQr` — `stopPropagation`);
  `NewTokenQrView` (token hidden by default, `onToggleToken` fires; copy calls
  clipboard + success toast; PNG vs SVG `src` prefix from `qr_code` first char);
  `ExistingDeviceInfoView` (Device ID + `window.location.origin`;
  `Aktiv`/`Abgelaufen` badge from `expires_at`); `QrCodeDialog` (header text new
  vs existing; close fires `onClose`; renders `NewTokenQrView` when `qrData`,
  `ExistingDeviceInfoView` when only `selectedDevice`).
- **`NotificationStatus`** — mock `../api/mobile` `getDeviceNotifications`:
  returns `null` (renders nothing) when the query is empty; renders the
  `7_days → '7 Tage Warnung'` label + `Fehlgeschlagen` when `success:false`.
- **Integration** (`__tests__/pages/MobileDevicesPage.test.tsx`) — mock
  `useMobileRegistration` + `useAuth`; a populated fixture renders the register
  card + a device row; `loading:true` → loading state; generate button wired to
  `handleGenerateToken`.

## Verification gates

- `MobileDevicesPage.tsx` < 500 lines (target ~100).
- `eslint .` — 0 errors.
- `npm run build` (tsc -b + vite) — green (`import type` for type-only imports —
  `verbatimModuleSyntax` enforced by `tsc -b`, not vitest; `TFunction`,
  `MobileDevice`, `MobileRegistrationToken`, `ReactNode` are type-only).
- `vitest run` — full suite green.
- Multi-agent whole-branch review — READY TO MERGE (field-for-field audit of
  every moved block, especially `handleGenerateToken`'s `localStorage` payload,
  the close-reset's conditional `refetchDevices`, the `qr_code` base64-prefix
  detection, and the deduped `mobileExpiry` at all three original call sites).
