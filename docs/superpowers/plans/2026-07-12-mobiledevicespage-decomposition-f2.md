# MobileDevicesPage.tsx Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose `client/src/pages/MobileDevicesPage.tsx` (613 lines) into a data/state hook, a pure date/expiry helper, and presentational components under `components/mobile-devices/`, byte-identical in behavior.

**Architecture:** A `useMobileRegistration()` hook owns all state, reads, and handlers. Pure `mobileDeviceDates.ts` dedupes date/expiry/time-ago logic. Seven presentational components render props-in/callbacks-in. The page becomes a thin orchestrator (~100 lines).

**Tech Stack:** React 18 + TypeScript (strict, `verbatimModuleSyntax`) + Vite + Tailwind + react-i18next + @tanstack/react-query + react-hot-toast + lucide-react + Vitest + @testing-library/react.

## Global Constraints

- **Behavior byte-identical.** No change to API calls, endpoints, query keys, `useMobileDevices` 10s polling, i18n keys, copy, Tailwind classes, `confirm(...)` wording, `localStorage` payload, close-reset semantics, `qr_code` base64-prefix detection, or `toLocaleString('de-DE')` formatting.
- **All strings verbatim** (predominantly hard-coded German). i18n migration is out of scope (issue #406).
- **Page stays** `pages/MobileDevicesPage.tsx`, `export default function MobileDevicesPage`, route `/mobile`.
- **Type-only imports** use `import type` (`verbatimModuleSyntax`, enforced by `tsc -b` / `npm run build` — NOT vitest). Applies to `MobileDevice`, `MobileRegistrationToken`, `TFunction`, `ReactNode`.
- **Presentational components**: props in, callbacks in, no fetching. Sole exception: `NotificationStatus` keeps its own `useQuery` (moved verbatim). `MobileDeviceCard` may call `useTranslation('common')` for display only.
- **Test hygiene (T7)**: assert role/text/title, never Tailwind classes. Mock `react-i18next` with `useTranslation: () => ({ t: (k) => k })`. **German-locale gotcha**: never assert on separator-formatted numbers/dates — assert plain values or i18n keys. Fixtures are complete real-type objects.
- **Windows/PowerShell**: no `&&`; use `;` or `if ($?) {}`. Run `npx tsc -b` before every commit. CRLF warnings on write are expected.
- New dir: `client/src/components/mobile-devices/`. Tests under `client/src/__tests__/components/mobile-devices/` and `client/src/__tests__/pages/`.

---

### Task 1: Pure date/expiry helper `mobileDeviceDates.ts`

**Files:**
- Create: `client/src/components/mobile-devices/mobileDeviceDates.ts`
- Test: `client/src/__tests__/components/mobile-devices/mobileDeviceDates.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `formatMobileDate(dateString: string | null): string`; `interface MobileExpiry { daysLeft: number; isExpired: boolean; isExpiringSoon: boolean }`; `mobileExpiry(expiresAt: string): MobileExpiry`; `mobileTimeAgo(dateString: string | null, t: TFunction): string`; `notificationTimeAgo(dateString: string): string`.

- [ ] **Step 1: Write the failing test**

```ts
// mobileDeviceDates.test.ts
import { describe, it, expect } from 'vitest';
import {
  formatMobileDate, mobileExpiry, mobileTimeAgo, notificationTimeAgo,
} from '../../../components/mobile-devices/mobileDeviceDates';

const tStub = ((k: string) => k) as unknown as Parameters<typeof mobileTimeAgo>[1];

describe('formatMobileDate', () => {
  it('returns Nie for null', () => {
    expect(formatMobileDate(null)).toBe('Nie');
  });
  it('returns a non-empty string for a date (no separator assertion)', () => {
    expect(formatMobileDate('2026-01-01T00:00:00Z').length).toBeGreaterThan(0);
  });
});

describe('mobileExpiry', () => {
  const iso = (msFromNow: number) => new Date(Date.now() + msFromNow).toISOString();
  const DAY = 86_400_000;
  it('far future: not expired, not soon', () => {
    const r = mobileExpiry(iso(30 * DAY));
    expect(r.isExpired).toBe(false);
    expect(r.isExpiringSoon).toBe(false);
  });
  it('within 7 days: soon, not expired', () => {
    const r = mobileExpiry(iso(3 * DAY));
    expect(r.isExpired).toBe(false);
    expect(r.isExpiringSoon).toBe(true);
  });
  it('past: expired', () => {
    const r = mobileExpiry(iso(-2 * DAY));
    expect(r.isExpired).toBe(true);
  });
});

describe('mobileTimeAgo', () => {
  it('null returns time.never key', () => {
    expect(mobileTimeAgo(null, tStub)).toBe('time.never');
  });
  it('under a minute returns time.justNow key', () => {
    expect(mobileTimeAgo(new Date(Date.now() - 5_000).toISOString(), tStub)).toBe('time.justNow');
  });
});

describe('notificationTimeAgo', () => {
  it('under a minute', () => {
    expect(notificationTimeAgo(new Date(Date.now() - 5_000).toISOString())).toBe('Gerade eben');
  });
  it('a few minutes', () => {
    expect(notificationTimeAgo(new Date(Date.now() - 120_000).toISOString())).toBe('Vor 2 Min');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/mobileDeviceDates.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```ts
// mobileDeviceDates.ts
import type { TFunction } from 'i18next';

export function formatMobileDate(dateString: string | null): string {
  if (!dateString) return 'Nie';
  const date = new Date(dateString);
  return date.toLocaleString('de-DE');
}

export interface MobileExpiry {
  daysLeft: number;
  isExpired: boolean;
  isExpiringSoon: boolean;
}

export function mobileExpiry(expiresAt: string): MobileExpiry {
  const expiresDate = new Date(expiresAt);
  const daysLeft = Math.ceil((expiresDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
  return { daysLeft, isExpired: daysLeft <= 0, isExpiringSoon: daysLeft <= 7 };
}

export function mobileTimeAgo(dateString: string | null, t: TFunction): string {
  if (!dateString) return t('time.never', 'Nie');
  const date = new Date(dateString);
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return t('time.justNow');
  if (seconds < 3600) return t('time.minutesAgo', { count: Math.floor(seconds / 60) });
  if (seconds < 86400) return t('time.hoursAgo', { count: Math.floor(seconds / 3600) });
  return t('time.daysAgo', { count: Math.floor(seconds / 86400) });
}

export function notificationTimeAgo(dateString: string): string {
  const sentDate = new Date(dateString);
  const seconds = Math.floor((Date.now() - sentDate.getTime()) / 1000);
  if (seconds < 60) return 'Gerade eben';
  if (seconds < 3600) return `Vor ${Math.floor(seconds / 60)} Min`;
  if (seconds < 86400) return `Vor ${Math.floor(seconds / 3600)} Std`;
  return `Vor ${Math.floor(seconds / 86400)} Tagen`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/mobileDeviceDates.test.ts`
Expected: PASS. Then `npx tsc -b`.

- [ ] **Step 5: Commit**

```
git add client/src/components/mobile-devices/mobileDeviceDates.ts client/src/__tests__/components/mobile-devices/mobileDeviceDates.test.ts
git commit -m "feat(mobile): add mobileDeviceDates helper (format/expiry/timeAgo) (#301)"
```

---

### Task 2: `useMobileRegistration` hook

**Files:**
- Create: `client/src/hooks/useMobileRegistration.ts`
- Test: `client/src/__tests__/hooks/useMobileRegistration.test.tsx`

**Interfaces:**
- Consumes: `generateMobileToken`, `getAvailableVpnTypes`, `deleteMobileDevice` + types `MobileRegistrationToken`, `MobileDevice` from `../api/mobile`; `queryKeys` from `../lib/queryKeys`; `useMobileDevices` from `./useMobileDevices`; `useConfirmDialog` from `./useConfirmDialog`.
- Produces: `useMobileRegistration(): UseMobileRegistrationResult` with the shape in the design doc (reads, form state, dialog state, handlers, `dialog`).

- [ ] **Step 1: Write the failing test**

```tsx
// useMobileRegistration.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const generateMobileToken = vi.fn();
const deleteMobileDevice = vi.fn();
const getAvailableVpnTypes = vi.fn(() => Promise.resolve(['wireguard']));
const refetch = vi.fn();
const confirmFn = vi.fn();
const toastError = vi.fn();

vi.mock('../../api/mobile', () => ({
  generateMobileToken: (...a: unknown[]) => generateMobileToken(...a),
  getAvailableVpnTypes: () => getAvailableVpnTypes(),
  deleteMobileDevice: (...a: unknown[]) => deleteMobileDevice(...a),
}));
vi.mock('../../hooks/useMobileDevices', () => ({
  useMobileDevices: () => ({ devices: [], loading: false, isFetching: false, refetch }),
}));
vi.mock('../../hooks/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: (...a: unknown[]) => confirmFn(...a), dialog: null }),
}));
vi.mock('react-hot-toast', () => ({ default: { error: (...a: unknown[]) => toastError(...a), success: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string, f?: string) => f ?? k }) }));

import { useMobileRegistration } from '../../hooks/useMobileRegistration';

const wrapper = ({ children }: { children: ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe('useMobileRegistration', () => {
  it('generate with empty name toasts and does not call API', async () => {
    const { result } = renderHook(() => useMobileRegistration(), { wrapper });
    await act(async () => { await result.current.handleGenerateToken(); });
    expect(toastError).toHaveBeenCalled();
    expect(generateMobileToken).not.toHaveBeenCalled();
  });

  it('generate with a name calls API, sets qrData, persists token, opens dialog', async () => {
    generateMobileToken.mockResolvedValue({ token: 'abc', qr_code: 'iVBOR', expires_at: '2026-01-01T00:00:00Z', device_token_validity_days: 90 });
    const { result } = renderHook(() => useMobileRegistration(), { wrapper });
    act(() => { result.current.setDeviceName('iPhone'); });
    await act(async () => { await result.current.handleGenerateToken(); });
    expect(generateMobileToken).toHaveBeenCalledWith(false, 'iPhone', 90, 'auto');
    expect(result.current.qrData).not.toBeNull();
    expect(result.current.showQrDialog).toBe(true);
    expect(localStorage.getItem('lastMobileToken')).toContain('iPhone');
  });

  it('delete with confirm=false does not call deleteMobileDevice', async () => {
    confirmFn.mockResolvedValue(false);
    const { result } = renderHook(() => useMobileRegistration(), { wrapper });
    await act(async () => { await result.current.handleDeleteDevice('id1', 'Phone'); });
    expect(deleteMobileDevice).not.toHaveBeenCalled();
  });

  it('closeQrDialog resets form and refetches when qrData was set', async () => {
    generateMobileToken.mockResolvedValue({ token: 'abc', qr_code: 'iVBOR', expires_at: '2026-01-01T00:00:00Z', device_token_validity_days: 90 });
    const { result } = renderHook(() => useMobileRegistration(), { wrapper });
    act(() => { result.current.setDeviceName('iPhone'); result.current.setIncludeVpn(true); });
    await act(async () => { await result.current.handleGenerateToken(); });
    refetch.mockClear();
    act(() => { result.current.closeQrDialog(); });
    await waitFor(() => expect(result.current.showQrDialog).toBe(false));
    expect(result.current.deviceName).toBe('');
    expect(result.current.includeVpn).toBe(false);
    expect(refetch).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/hooks/useMobileRegistration.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```ts
// useMobileRegistration.ts
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import type { ReactNode } from 'react';
import {
  generateMobileToken, getAvailableVpnTypes, deleteMobileDevice,
  type MobileRegistrationToken, type MobileDevice,
} from '../api/mobile';
import { queryKeys } from '../lib/queryKeys';
import { useMobileDevices } from './useMobileDevices';
import { useConfirmDialog } from './useConfirmDialog';

export interface UseMobileRegistrationResult {
  devices: MobileDevice[];
  loading: boolean;
  isFetching: boolean;
  availableVpnTypes: string[];
  deviceName: string;
  setDeviceName: (v: string) => void;
  tokenValidityDays: number;
  setTokenValidityDays: (v: number) => void;
  includeVpn: boolean;
  setIncludeVpn: (v: boolean) => void;
  vpnType: string;
  setVpnType: (v: string) => void;
  generating: boolean;
  showQrDialog: boolean;
  qrData: MobileRegistrationToken | null;
  selectedDevice: MobileDevice | null;
  showToken: boolean;
  toggleShowToken: () => void;
  handleGenerateToken: () => Promise<void>;
  handleDeleteDevice: (deviceId: string, deviceName: string) => Promise<void>;
  handleShowDeviceQr: (device: MobileDevice) => void;
  refetchDevices: () => void;
  closeQrDialog: () => void;
  dialog: ReactNode;
}

export function useMobileRegistration(): UseMobileRegistrationResult {
  const { t } = useTranslation('common');
  const { confirm, dialog } = useConfirmDialog();

  const { devices, loading, isFetching, refetch: refetchDevices } = useMobileDevices();
  const { data: availableVpnTypes = [] } = useQuery({
    queryKey: queryKeys.mobile.vpnTypes(),
    queryFn: getAvailableVpnTypes,
  });

  const [qrData, setQrData] = useState<MobileRegistrationToken | null>(null);
  const [showQrDialog, setShowQrDialog] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<MobileDevice | null>(null);
  const [includeVpn, setIncludeVpn] = useState(false);
  const [vpnType, setVpnType] = useState<string>('auto');
  const [deviceName, setDeviceName] = useState('');
  const [tokenValidityDays, setTokenValidityDays] = useState(90);
  const [generating, setGenerating] = useState(false);
  const [showToken, setShowToken] = useState(false);

  const handleGenerateToken = async () => {
    if (!deviceName.trim()) {
      toast.error(t('mobile.enterDeviceName', 'Bitte Gerätenamen eingeben'));
      return;
    }
    try {
      setGenerating(true);
      const token = await generateMobileToken(includeVpn, deviceName.trim(), tokenValidityDays, vpnType);
      setQrData(token);
      try {
        const stored = { ...token, device_name: deviceName.trim(), include_vpn: includeVpn };
        localStorage.setItem('lastMobileToken', JSON.stringify(stored));
      } catch {
        // localStorage may be full or unavailable
      }
      setShowQrDialog(true);
    } catch (error: unknown) {
      const errorMsg = error instanceof Error ? error.message : 'QR-Code konnte nicht generiert werden';
      toast.error(errorMsg);
    } finally {
      setGenerating(false);
    }
  };

  const handleDeleteDevice = async (deviceId: string, deviceName: string) => {
    const ok = await confirm(`Gerät "${deviceName}" wirklich löschen?`, { title: 'Gerät löschen', variant: 'danger', confirmLabel: 'Löschen' });
    if (!ok) return;
    try {
      await deleteMobileDevice(deviceId);
      await refetchDevices();
    } catch {
      toast.error(t('mobile.deleteFailed', 'Gerät konnte nicht gelöscht werden'));
      await refetchDevices();
    }
  };

  const handleShowDeviceQr = (device: MobileDevice) => {
    setSelectedDevice(device);
    setShowQrDialog(true);
  };

  const closeQrDialog = () => {
    setShowQrDialog(false);
    setQrData(null);
    setSelectedDevice(null);
    setDeviceName('');
    setIncludeVpn(false);
    setVpnType('auto');
    setShowToken(false);
    if (qrData) void refetchDevices();
  };

  return {
    devices, loading, isFetching, availableVpnTypes,
    deviceName, setDeviceName, tokenValidityDays, setTokenValidityDays,
    includeVpn, setIncludeVpn, vpnType, setVpnType, generating,
    showQrDialog, qrData, selectedDevice, showToken,
    toggleShowToken: () => setShowToken((s) => !s),
    handleGenerateToken, handleDeleteDevice, handleShowDeviceQr,
    refetchDevices, closeQrDialog, dialog,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/hooks/useMobileRegistration.test.tsx`
Expected: PASS. Then `npx tsc -b`.

**Note on the delete-error `deviceName` shadow:** the original nests a parameter
`deviceName` inside `handleDeleteDevice` that shadows the outer state
`deviceName` — this is intentional and preserved (the confirm string uses the
parameter). Keep the parameter name.

**Note on `toggleShowToken`:** the original toggle was
`onClick={() => setShowToken(!showToken)}`. The hook exposes it as
`toggleShowToken: () => setShowToken((s) => !s)` — the functional updater is
behaviorally identical for a boolean toggle (not a behavior change).

**Note on `refetchDevices` type:** `useMobileDevices().refetch` is
`() => Promise<unknown>`; exposing it as `refetchDevices: () => void` is a valid
widening (a Promise-returning function is assignable to `() => void`). The
`void refetchDevices()` in `closeQrDialog` matches the original.

- [ ] **Step 5: Commit**

```
git add client/src/hooks/useMobileRegistration.ts client/src/__tests__/hooks/useMobileRegistration.test.tsx
git commit -m "feat(mobile): add useMobileRegistration hook (state + handlers) (#301)"
```

---

### Task 3: `NotificationStatus` component

**Files:**
- Create: `client/src/components/mobile-devices/NotificationStatus.tsx`
- Test: `client/src/__tests__/components/mobile-devices/NotificationStatus.test.tsx`

**Interfaces:**
- Consumes: `getDeviceNotifications` from `../../api/mobile`; `queryKeys` from `../../lib/queryKeys`; `notificationTimeAgo` from `./mobileDeviceDates`.
- Produces: `NotificationStatus({ deviceId: string })`.

- [ ] **Step 1: Write the failing test**

```tsx
// NotificationStatus.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const getDeviceNotifications = vi.fn();
vi.mock('../../../api/mobile', () => ({
  getDeviceNotifications: (...a: unknown[]) => getDeviceNotifications(...a),
}));

import { NotificationStatus } from '../../../components/mobile-devices/NotificationStatus';

const wrapper = ({ children }: { children: ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

describe('NotificationStatus', () => {
  it('renders nothing when there are no notifications', async () => {
    getDeviceNotifications.mockResolvedValue([]);
    const { container } = render(<NotificationStatus deviceId="d1" />, { wrapper });
    // give the query a tick
    await Promise.resolve();
    expect(container.textContent).toBe('');
  });

  it('renders the label and Fehlgeschlagen for a failed notification', async () => {
    getDeviceNotifications.mockResolvedValue([
      { notification_type: '7_days', sent_at: new Date().toISOString(), success: false },
    ]);
    render(<NotificationStatus deviceId="d1" />, { wrapper });
    expect(await screen.findByText('7 Tage Warnung')).toBeInTheDocument();
    expect(screen.getByText('Fehlgeschlagen')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/NotificationStatus.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation** (move verbatim from page lines 571–612, swap inline timeAgo for `notificationTimeAgo`)

```tsx
// NotificationStatus.tsx
import { useQuery } from '@tanstack/react-query';
import { Bell } from 'lucide-react';
import { getDeviceNotifications } from '../../api/mobile';
import { queryKeys } from '../../lib/queryKeys';
import { notificationTimeAgo } from './mobileDeviceDates';

/**
 * Component to display last notification sent to device.
 */
export function NotificationStatus({ deviceId }: { deviceId: string }) {
  const { data: notifications = [] } = useQuery({
    queryKey: queryKeys.mobile.deviceNotifications(deviceId),
    queryFn: () => getDeviceNotifications(deviceId, 1),
  });
  const lastNotification = notifications[0] ?? null;

  if (!lastNotification) return null;

  const notificationLabels: Record<string, string> = {
    '7_days': '7 Tage Warnung',
    '3_days': '3 Tage Warnung',
    '1_hour': '1 Stunde Warnung',
  };

  const notificationLabel = notificationLabels[lastNotification.notification_type] || lastNotification.notification_type;
  const timeAgo = notificationTimeAgo(lastNotification.sent_at);

  return (
    <div className="mt-3 pt-3 border-t border-slate-700/50">
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <Bell className={`w-3.5 h-3.5 ${
          lastNotification.success ? 'text-sky-400' : 'text-red-400'
        }`} />
        <span className="font-medium text-slate-300">Letzte Benachrichtigung:</span>
        <span>{notificationLabel}</span>
        <span className="text-slate-500">•</span>
        <span>{timeAgo}</span>
        {!lastNotification.success && (
          <span className="text-red-400 font-semibold">Fehlgeschlagen</span>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/NotificationStatus.test.tsx`
Expected: PASS. Then `npx tsc -b`.

- [ ] **Step 5: Commit**

```
git add client/src/components/mobile-devices/NotificationStatus.tsx client/src/__tests__/components/mobile-devices/NotificationStatus.test.tsx
git commit -m "feat(mobile): extract NotificationStatus component (#301)"
```

---

### Task 4: `MobileDeviceCard` component

**Files:**
- Create: `client/src/components/mobile-devices/MobileDeviceCard.tsx`
- Test: `client/src/__tests__/components/mobile-devices/MobileDeviceCard.test.tsx`

**Interfaces:**
- Consumes: `MobileDevice` from `../../api/mobile`; `formatMobileDate`, `mobileTimeAgo`, `mobileExpiry` from `./mobileDeviceDates`; `NotificationStatus` from `./NotificationStatus`; `useTranslation` from `react-i18next`.
- Produces: `MobileDeviceCard({ device: MobileDevice; isAdmin: boolean; onShowQr: (device: MobileDevice) => void; onDelete: (id: string, name: string) => void })`.

- [ ] **Step 1: Write the failing test**

```tsx
// MobileDeviceCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { MobileDevice } from '../../../api/mobile';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('../../../components/mobile-devices/NotificationStatus', () => ({
  NotificationStatus: () => null,
}));
import { MobileDeviceCard } from '../../../components/mobile-devices/MobileDeviceCard';

const device = (over: Partial<MobileDevice> = {}): MobileDevice => ({
  id: 'dev-1', device_name: 'iPhone 15', device_type: 'ios', is_active: true,
  created_at: '2026-01-01T00:00:00Z', expires_at: null,
  device_model: null, os_version: null, app_version: null,
  last_sync: null, last_seen: null, username: null,
  ...over,
} as MobileDevice);

describe('MobileDeviceCard', () => {
  it('shows the device name and Aktiv when active', () => {
    render(<MobileDeviceCard device={device()} isAdmin={false} onShowQr={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText('iPhone 15')).toBeInTheDocument();
    expect(screen.getByText('Aktiv')).toBeInTheDocument();
  });

  it('shows Abgelaufen badge for a past expiry', () => {
    const past = new Date(Date.now() - 5 * 86_400_000).toISOString();
    render(<MobileDeviceCard device={device({ expires_at: past })} isAdmin={false} onShowQr={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText('Abgelaufen')).toBeInTheDocument();
  });

  it('delete button fires onDelete and not onShowQr (stopPropagation)', () => {
    const onShowQr = vi.fn();
    const onDelete = vi.fn();
    render(<MobileDeviceCard device={device()} isAdmin={false} onShowQr={onShowQr} onDelete={onDelete} />);
    fireEvent.click(screen.getByTitle('Gerät löschen'));
    expect(onDelete).toHaveBeenCalledWith('dev-1', 'iPhone 15');
    expect(onShowQr).not.toHaveBeenCalled();
  });

  it('card click fires onShowQr', () => {
    const onShowQr = vi.fn();
    render(<MobileDeviceCard device={device()} isAdmin={false} onShowQr={onShowQr} onDelete={vi.fn()} />);
    fireEvent.click(screen.getByTitle('Klicken um QR-Code anzuzeigen'));
    expect(onShowQr).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/MobileDeviceCard.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation** (move page lines 269–365 verbatim; wire helpers)

Port the `<div key=... onClick={() => onShowQr(device)} title="Klicken um QR-Code anzuzeigen">` card verbatim. Replace `formatDate(...)` → `formatMobileDate(...)`, `getTimeAgo(device.last_sync ?? device.last_seen ?? null)` → `mobileTimeAgo(device.last_sync ?? device.last_seen ?? null, t)` (with `const { t } = useTranslation('common');`), and the inline expiry IIFE → `const exp = mobileExpiry(device.expires_at)` reusing `exp.isExpired`/`exp.isExpiringSoon`/`exp.daysLeft` (keep the `{device.expires_at && (() => { ... })()}` structure but source the three values from `mobileExpiry`). Delete button keeps `onClick={(e) => { e.stopPropagation(); onDelete(device.id, device.device_name); }}`. Render `<NotificationStatus deviceId={device.id} />`. Import icons `Smartphone, Wifi, WifiOff, Calendar, Clock, User, Trash2` from `lucide-react`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/MobileDeviceCard.test.tsx`
Expected: PASS. Then `npx tsc -b`.

- [ ] **Step 5: Commit**

```
git add client/src/components/mobile-devices/MobileDeviceCard.tsx client/src/__tests__/components/mobile-devices/MobileDeviceCard.test.tsx
git commit -m "feat(mobile): extract MobileDeviceCard component (#301)"
```

---

### Task 5: `MobileDevicesList` component

**Files:**
- Create: `client/src/components/mobile-devices/MobileDevicesList.tsx`
- Test: `client/src/__tests__/components/mobile-devices/MobileDevicesList.test.tsx`

**Interfaces:**
- Consumes: `MobileDevice` from `../../api/mobile`; `MobileDeviceCard` from `./MobileDeviceCard`.
- Produces: `MobileDevicesList({ devices: MobileDevice[]; loading: boolean; isFetching: boolean; isAdmin: boolean; onRefresh: () => void; onShowQr: (device: MobileDevice) => void; onDelete: (id: string, name: string) => void })`.

- [ ] **Step 1: Write the failing test**

```tsx
// MobileDevicesList.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { MobileDevice } from '../../../api/mobile';

vi.mock('../../../components/mobile-devices/MobileDeviceCard', () => ({
  MobileDeviceCard: ({ device }: { device: MobileDevice }) => <div>card:{device.device_name}</div>,
}));
import { MobileDevicesList } from '../../../components/mobile-devices/MobileDevicesList';

const device = (over: Partial<MobileDevice> = {}): MobileDevice => ({
  id: 'dev-1', device_name: 'iPhone 15', device_type: 'ios', is_active: true,
  created_at: '2026-01-01T00:00:00Z', expires_at: null,
} as MobileDevice);

const base = { isAdmin: false, onRefresh: vi.fn(), onShowQr: vi.fn(), onDelete: vi.fn() };

describe('MobileDevicesList', () => {
  it('shows loading state', () => {
    render(<MobileDevicesList devices={[]} loading isFetching={false} {...base} />);
    expect(screen.getByText('Lade Geräte...')).toBeInTheDocument();
  });
  it('shows empty state', () => {
    render(<MobileDevicesList devices={[]} loading={false} isFetching={false} {...base} />);
    expect(screen.getByText('Keine Geräte registriert')).toBeInTheDocument();
  });
  it('renders a card per device and count', () => {
    render(<MobileDevicesList devices={[device(), device({ id: 'dev-2', device_name: 'Pixel' })]} loading={false} isFetching={false} {...base} />);
    expect(screen.getByText('card:iPhone 15')).toBeInTheDocument();
    expect(screen.getByText('card:Pixel')).toBeInTheDocument();
    expect(screen.getByText('Registrierte Geräte (2)')).toBeInTheDocument();
  });
  it('refresh button fires onRefresh', () => {
    const onRefresh = vi.fn();
    render(<MobileDevicesList devices={[]} loading={false} isFetching={false} {...base} onRefresh={onRefresh} />);
    fireEvent.click(screen.getByTitle('Aktualisieren'));
    expect(onRefresh).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/MobileDevicesList.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation** (move page lines 240–369 verbatim; the `devices.map` renders `<MobileDeviceCard device={device} isAdmin={isAdmin} onShowQr={onShowQr} onDelete={onDelete} key={device.id} />`; refresh button `onClick={onRefresh}`)

Import `Smartphone, RefreshCw` from `lucide-react`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/MobileDevicesList.test.tsx`
Expected: PASS. Then `npx tsc -b`.

- [ ] **Step 5: Commit**

```
git add client/src/components/mobile-devices/MobileDevicesList.tsx client/src/__tests__/components/mobile-devices/MobileDevicesList.test.tsx
git commit -m "feat(mobile): extract MobileDevicesList component (#301)"
```

---

### Task 6: `RegisterDeviceCard` component

**Files:**
- Create: `client/src/components/mobile-devices/RegisterDeviceCard.tsx`
- Test: `client/src/__tests__/components/mobile-devices/RegisterDeviceCard.test.tsx`

**Interfaces:**
- Consumes: icons from `lucide-react`.
- Produces: `RegisterDeviceCard({ deviceName: string; onDeviceNameChange: (v: string) => void; tokenValidityDays: number; onValidityChange: (v: number) => void; includeVpn: boolean; onIncludeVpnChange: (v: boolean) => void; vpnType: string; onVpnTypeChange: (v: string) => void; availableVpnTypes: string[]; generating: boolean; onGenerate: () => void })`.

- [ ] **Step 1: Write the failing test**

```tsx
// RegisterDeviceCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RegisterDeviceCard } from '../../../components/mobile-devices/RegisterDeviceCard';

const base = {
  deviceName: '', onDeviceNameChange: vi.fn(),
  tokenValidityDays: 90, onValidityChange: vi.fn(),
  includeVpn: false, onIncludeVpnChange: vi.fn(),
  vpnType: 'auto', onVpnTypeChange: vi.fn(),
  availableVpnTypes: ['wireguard'], generating: false, onGenerate: vi.fn(),
};

describe('RegisterDeviceCard', () => {
  it('typing a name fires onDeviceNameChange', () => {
    const onDeviceNameChange = vi.fn();
    render(<RegisterDeviceCard {...base} onDeviceNameChange={onDeviceNameChange} />);
    fireEvent.change(screen.getByPlaceholderText('z.B. iPhone 15, Samsung Galaxy S24'), { target: { value: 'X' } });
    expect(onDeviceNameChange).toHaveBeenCalledWith('X');
  });
  it('generate button is disabled when name blank', () => {
    render(<RegisterDeviceCard {...base} />);
    expect(screen.getByText('QR-Code generieren').closest('button')).toBeDisabled();
  });
  it('generate fires onGenerate when name present', () => {
    const onGenerate = vi.fn();
    render(<RegisterDeviceCard {...base} deviceName="iPhone" onGenerate={onGenerate} />);
    fireEvent.click(screen.getByText('QR-Code generieren').closest('button')!);
    expect(onGenerate).toHaveBeenCalled();
  });
  it('shows VPN type selector only when >1 vpn types and includeVpn', () => {
    const { rerender } = render(<RegisterDeviceCard {...base} includeVpn availableVpnTypes={['wireguard']} />);
    expect(screen.queryByText('Automatisch')).not.toBeInTheDocument();
    rerender(<RegisterDeviceCard {...base} includeVpn availableVpnTypes={['fritzbox', 'wireguard']} />);
    expect(screen.getByText('Automatisch')).toBeInTheDocument();
    fireEvent.click(screen.getByText('NAS-VPN (WireGuard)'));
    expect(base.onVpnTypeChange).toHaveBeenCalledWith('wireguard');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/RegisterDeviceCard.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation** (move page lines 104–237 verbatim). Map: `value={deviceName}` + `onChange={(e) => onDeviceNameChange(e.target.value)}`; slider `onChange={(e) => onValidityChange(Number(e.target.value))}` (keep the `linear-gradient` inline style + `((tokenValidityDays - 30) / 150) * 100` exactly); checkbox `onChange={(e) => onIncludeVpnChange(e.target.checked)}`; VPN-type buttons `onClick={() => onVpnTypeChange(opt.value)}`; generate button `onClick={onGenerate}` + `disabled={generating || !deviceName.trim()}`. Import `QrCode as QrCodeIcon, RefreshCw, Plus` from `lucide-react`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/RegisterDeviceCard.test.tsx`
Expected: PASS. Then `npx tsc -b`.

- [ ] **Step 5: Commit**

```
git add client/src/components/mobile-devices/RegisterDeviceCard.tsx client/src/__tests__/components/mobile-devices/RegisterDeviceCard.test.tsx
git commit -m "feat(mobile): extract RegisterDeviceCard component (#301)"
```

---

### Task 7: `NewTokenQrView` component

**Files:**
- Create: `client/src/components/mobile-devices/NewTokenQrView.tsx`
- Test: `client/src/__tests__/components/mobile-devices/NewTokenQrView.test.tsx`

**Interfaces:**
- Consumes: `MobileRegistrationToken` from `../../api/mobile`; `toast` from `react-hot-toast`; icons from `lucide-react`.
- Produces: `NewTokenQrView({ qrData: MobileRegistrationToken; showToken: boolean; onToggleToken: () => void })`.

- [ ] **Step 1: Write the failing test**

```tsx
// NewTokenQrView.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { MobileRegistrationToken } from '../../../api/mobile';

const success = vi.fn();
vi.mock('react-hot-toast', () => ({ default: { success: (...a: unknown[]) => success(...a) } }));
import { NewTokenQrView } from '../../../components/mobile-devices/NewTokenQrView';

const token = (over: Partial<MobileRegistrationToken> = {}): MobileRegistrationToken => ({
  token: 'tok-abc', qr_code: 'iVBORpng', expires_at: '2026-06-01T12:00:00Z',
  device_token_validity_days: 90, vpn_config: null, vpn_fallback: false,
  ...over,
} as MobileRegistrationToken);

describe('NewTokenQrView', () => {
  it('toggle button fires onToggleToken', () => {
    const onToggleToken = vi.fn();
    render(<NewTokenQrView qrData={token()} showToken={false} onToggleToken={onToggleToken} />);
    fireEvent.click(screen.getByText('Token manuell anzeigen'));
    expect(onToggleToken).toHaveBeenCalled();
  });
  it('shows the token and copies on click when showToken', () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn() } });
    render(<NewTokenQrView qrData={token()} showToken onToggleToken={vi.fn()} />);
    expect(screen.getByText('tok-abc')).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('Kopieren'));
    expect(success).toHaveBeenCalledWith('Token kopiert');
  });
  it('uses image/png src prefix when qr_code starts with iVBOR', () => {
    render(<NewTokenQrView qrData={token({ qr_code: 'iVBORxyz' })} showToken={false} onToggleToken={vi.fn()} />);
    expect(screen.getByAltText('QR Code').getAttribute('src')).toContain('data:image/png;base64,iVBORxyz');
  });
  it('uses image/svg+xml when qr_code does not start with iVBOR', () => {
    render(<NewTokenQrView qrData={token({ qr_code: 'PHN2Zz' })} showToken={false} onToggleToken={vi.fn()} />);
    expect(screen.getByAltText('QR Code').getAttribute('src')).toContain('data:image/svg+xml;base64,PHN2Zz');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/NewTokenQrView.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation** (move page lines 396–464 verbatim, wrapped in a fragment). Keep the `src={\`data:${qrData.qr_code.startsWith('iVBOR') ? 'image/png' : 'image/svg+xml'};base64,${qrData.qr_code}\`}`, the toggle button `onClick={onToggleToken}` showing `showToken ? 'Token verbergen' : 'Token manuell anzeigen'`, the copy button (`navigator.clipboard.writeText(qrData.token)` + `toast.success('Token kopiert')`), and the `toLocaleString('de-DE')` expiry line. Import `Eye, EyeOff, Copy` from `lucide-react`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/NewTokenQrView.test.tsx`
Expected: PASS. Then `npx tsc -b`.

- [ ] **Step 5: Commit**

```
git add client/src/components/mobile-devices/NewTokenQrView.tsx client/src/__tests__/components/mobile-devices/NewTokenQrView.test.tsx
git commit -m "feat(mobile): extract NewTokenQrView component (#301)"
```

---

### Task 8: `ExistingDeviceInfoView` component

**Files:**
- Create: `client/src/components/mobile-devices/ExistingDeviceInfoView.tsx`
- Test: `client/src/__tests__/components/mobile-devices/ExistingDeviceInfoView.test.tsx`

**Interfaces:**
- Consumes: `MobileDevice` from `../../api/mobile`; `formatMobileDate`, `mobileExpiry` from `./mobileDeviceDates`; icons from `lucide-react`.
- Produces: `ExistingDeviceInfoView({ device: MobileDevice; isAdmin: boolean })`.

- [ ] **Step 1: Write the failing test**

```tsx
// ExistingDeviceInfoView.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { MobileDevice } from '../../../api/mobile';
import { ExistingDeviceInfoView } from '../../../components/mobile-devices/ExistingDeviceInfoView';

const device = (over: Partial<MobileDevice> = {}): MobileDevice => ({
  id: 'dev-xyz', device_name: 'iPhone', device_type: 'ios', is_active: true,
  created_at: '2026-01-01T00:00:00Z', expires_at: null, username: null,
  ...over,
} as MobileDevice);

describe('ExistingDeviceInfoView', () => {
  it('renders device id and origin', () => {
    render(<ExistingDeviceInfoView device={device()} isAdmin={false} />);
    expect(screen.getByText('dev-xyz')).toBeInTheDocument();
    expect(screen.getByText('Registriertes Gerät', { exact: false })).toBeInTheDocument();
  });
  it('shows Aktiv badge for a far-future expiry', () => {
    const future = new Date(Date.now() + 60 * 86_400_000).toISOString();
    render(<ExistingDeviceInfoView device={device({ expires_at: future })} isAdmin={false} />);
    expect(screen.getByText('Aktiv')).toBeInTheDocument();
  });
  it('shows Abgelaufen badge for a past expiry', () => {
    const past = new Date(Date.now() - 60 * 86_400_000).toISOString();
    render(<ExistingDeviceInfoView device={device({ expires_at: past })} isAdmin={false} />);
    expect(screen.getByText('Abgelaufen')).toBeInTheDocument();
  });
  it('shows the username row only when isAdmin', () => {
    const { rerender } = render(<ExistingDeviceInfoView device={device({ username: 'bob' })} isAdmin={false} />);
    expect(screen.queryByText('Benutzer:')).not.toBeInTheDocument();
    rerender(<ExistingDeviceInfoView device={device({ username: 'bob' })} isAdmin />);
    expect(screen.getByText('Benutzer:')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/ExistingDeviceInfoView.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation** (move page lines 465–559 verbatim, wrapped in a fragment). Replace both inline expiry IIFEs with `mobileExpiry(device.expires_at)` — preserve the color ternary `isExpired ? 'text-red-400' : isExpiringSoon ? 'text-orange-400' : 'text-green-400'` and the badge branch (`Abgelaufen` / `{daysLeft} Tage` / `Aktiv`). Replace `formatDate` → `formatMobileDate`. Use `window.location.origin`, `device.id`, `device.is_active`. Import `Smartphone, Calendar, User, QrCode as QrCodeIcon, Trash2` from `lucide-react`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/ExistingDeviceInfoView.test.tsx`
Expected: PASS. Then `npx tsc -b`.

- [ ] **Step 5: Commit**

```
git add client/src/components/mobile-devices/ExistingDeviceInfoView.tsx client/src/__tests__/components/mobile-devices/ExistingDeviceInfoView.test.tsx
git commit -m "feat(mobile): extract ExistingDeviceInfoView component (#301)"
```

---

### Task 9: `QrCodeDialog` shell + barrel

**Files:**
- Create: `client/src/components/mobile-devices/QrCodeDialog.tsx`
- Create: `client/src/components/mobile-devices/index.ts`
- Test: `client/src/__tests__/components/mobile-devices/QrCodeDialog.test.tsx`

**Interfaces:**
- Consumes: `MobileRegistrationToken`, `MobileDevice` from `../../api/mobile`; `NewTokenQrView` from `./NewTokenQrView`; `ExistingDeviceInfoView` from `./ExistingDeviceInfoView`.
- Produces: `QrCodeDialog({ qrData: MobileRegistrationToken | null; selectedDevice: MobileDevice | null; isAdmin: boolean; showToken: boolean; onToggleToken: () => void; onClose: () => void })`. Barrel `index.ts` re-exports all seven components + the four helpers from `mobileDeviceDates`.

- [ ] **Step 1: Write the failing test**

```tsx
// QrCodeDialog.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { MobileRegistrationToken, MobileDevice } from '../../../api/mobile';

vi.mock('../../../components/mobile-devices/NewTokenQrView', () => ({
  NewTokenQrView: () => <div>new-token-view</div>,
}));
vi.mock('../../../components/mobile-devices/ExistingDeviceInfoView', () => ({
  ExistingDeviceInfoView: () => <div>existing-device-view</div>,
}));
import { QrCodeDialog } from '../../../components/mobile-devices/QrCodeDialog';

const token = { token: 't', qr_code: 'iVBOR', expires_at: '2026-01-01T00:00:00Z', device_token_validity_days: 90 } as MobileRegistrationToken;
const device = { id: 'd1', device_name: 'iPhone' } as MobileDevice;
const base = { isAdmin: false, showToken: false, onToggleToken: vi.fn(), onClose: vi.fn() };

describe('QrCodeDialog', () => {
  it('renders new-token header and view when qrData is set', () => {
    render(<QrCodeDialog {...base} qrData={token} selectedDevice={null} />);
    expect(screen.getByText('QR-Code für Mobile App')).toBeInTheDocument();
    expect(screen.getByText('new-token-view')).toBeInTheDocument();
  });
  it('renders existing-device header and view when only selectedDevice is set', () => {
    render(<QrCodeDialog {...base} qrData={null} selectedDevice={device} />);
    expect(screen.getByText('QR-Code: iPhone')).toBeInTheDocument();
    expect(screen.getByText('existing-device-view')).toBeInTheDocument();
  });
  it('close button fires onClose', () => {
    const onClose = vi.fn();
    render(<QrCodeDialog {...base} qrData={token} selectedDevice={null} onClose={onClose} />);
    fireEvent.click(screen.getByText('✕'));
    expect(onClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/QrCodeDialog.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```tsx
// QrCodeDialog.tsx
import type { MobileRegistrationToken, MobileDevice } from '../../api/mobile';
import { NewTokenQrView } from './NewTokenQrView';
import { ExistingDeviceInfoView } from './ExistingDeviceInfoView';

export function QrCodeDialog({
  qrData, selectedDevice, isAdmin, showToken, onToggleToken, onClose,
}: {
  qrData: MobileRegistrationToken | null;
  selectedDevice: MobileDevice | null;
  isAdmin: boolean;
  showToken: boolean;
  onToggleToken: () => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-2 sm:p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-md h-full sm:h-auto max-h-[100vh] sm:max-h-[90vh] overflow-y-auto p-4 sm:p-6">
        <div className="flex items-center justify-between mb-4 gap-2">
          <h3 className="text-lg sm:text-xl font-semibold text-white truncate">
            {qrData ? 'QR-Code für Mobile App' : `QR-Code: ${selectedDevice?.device_name}`}
          </h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors p-2 -mr-2 touch-manipulation active:scale-95 min-w-[44px] min-h-[44px] flex items-center justify-center flex-shrink-0"
          >
            ✕
          </button>
        </div>

        {qrData ? (
          <NewTokenQrView qrData={qrData} showToken={showToken} onToggleToken={onToggleToken} />
        ) : selectedDevice ? (
          <ExistingDeviceInfoView device={selectedDevice} isAdmin={isAdmin} />
        ) : null}
      </div>
    </div>
  );
}
```

```ts
// index.ts
export { RegisterDeviceCard } from './RegisterDeviceCard';
export { MobileDevicesList } from './MobileDevicesList';
export { MobileDeviceCard } from './MobileDeviceCard';
export { NotificationStatus } from './NotificationStatus';
export { QrCodeDialog } from './QrCodeDialog';
export { NewTokenQrView } from './NewTokenQrView';
export { ExistingDeviceInfoView } from './ExistingDeviceInfoView';
export {
  formatMobileDate, mobileExpiry, mobileTimeAgo, notificationTimeAgo,
  type MobileExpiry,
} from './mobileDeviceDates';
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/mobile-devices/QrCodeDialog.test.tsx`
Expected: PASS. Then `npx tsc -b`.

- [ ] **Step 5: Commit**

```
git add client/src/components/mobile-devices/QrCodeDialog.tsx client/src/components/mobile-devices/index.ts client/src/__tests__/components/mobile-devices/QrCodeDialog.test.tsx
git commit -m "feat(mobile): extract QrCodeDialog shell + barrel (#301)"
```

---

### Task 10: Rewire `MobileDevicesPage.tsx` orchestrator + integration test

**Files:**
- Modify: `client/src/pages/MobileDevicesPage.tsx` (replace body; keep default export + path)
- Test: `client/src/__tests__/pages/MobileDevicesPage.test.tsx`

**Interfaces:**
- Consumes: `useMobileRegistration` from `../hooks/useMobileRegistration`; `useAuth` from `../contexts/AuthContext`; `RegisterDeviceCard`, `MobileDevicesList`, `QrCodeDialog` from `../components/mobile-devices`.
- Produces: `export default function MobileDevicesPage()`.

- [ ] **Step 1: Write the failing integration test**

```tsx
// MobileDevicesPage.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { MobileDevice } from '../../api/mobile';

const hookState: Record<string, unknown> = {};
vi.mock('../../hooks/useMobileRegistration', () => ({
  useMobileRegistration: () => hookState,
}));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ isAdmin: true }) }));
vi.mock('../../components/mobile-devices', () => ({
  RegisterDeviceCard: () => <div>register-card</div>,
  MobileDevicesList: ({ devices }: { devices: MobileDevice[] }) => <div>list:{devices.length}</div>,
  QrCodeDialog: () => <div>qr-dialog</div>,
}));
import MobileDevicesPage from '../../pages/MobileDevicesPage';

function setHook(over: Record<string, unknown> = {}) {
  Object.assign(hookState, {
    devices: [], loading: false, isFetching: false, availableVpnTypes: [],
    deviceName: '', setDeviceName: vi.fn(), tokenValidityDays: 90, setTokenValidityDays: vi.fn(),
    includeVpn: false, setIncludeVpn: vi.fn(), vpnType: 'auto', setVpnType: vi.fn(), generating: false,
    showQrDialog: false, qrData: null, selectedDevice: null, showToken: false, toggleShowToken: vi.fn(),
    handleGenerateToken: vi.fn(), handleDeleteDevice: vi.fn(), handleShowDeviceQr: vi.fn(),
    refetchDevices: vi.fn(), closeQrDialog: vi.fn(), dialog: null, ...over,
  });
}

describe('MobileDevicesPage', () => {
  it('renders header, register card and list', () => {
    setHook({ devices: [{ id: 'd1' } as MobileDevice] });
    render(<MobileDevicesPage />);
    expect(screen.getByText('Mobile Geräte')).toBeInTheDocument();
    expect(screen.getByText('register-card')).toBeInTheDocument();
    expect(screen.getByText('list:1')).toBeInTheDocument();
  });
  it('does not render the dialog when showQrDialog is false', () => {
    setHook();
    render(<MobileDevicesPage />);
    expect(screen.queryByText('qr-dialog')).not.toBeInTheDocument();
  });
  it('renders the dialog when showQrDialog and qrData are set', () => {
    setHook({ showQrDialog: true, qrData: { token: 't' } });
    render(<MobileDevicesPage />);
    expect(screen.getByText('qr-dialog')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/pages/MobileDevicesPage.test.tsx`
Expected: FAIL (page still has old body; `useMobileRegistration` mock unused → likely renders old markup and fails on `register-card`).

- [ ] **Step 3: Rewrite the page**

```tsx
// MobileDevicesPage.tsx
import { useMobileRegistration } from '../hooks/useMobileRegistration';
import { useAuth } from '../contexts/AuthContext';
import { RegisterDeviceCard, MobileDevicesList, QrCodeDialog } from '../components/mobile-devices';

export default function MobileDevicesPage() {
  const { isAdmin } = useAuth();
  const {
    devices, loading, isFetching, availableVpnTypes,
    deviceName, setDeviceName, tokenValidityDays, setTokenValidityDays,
    includeVpn, setIncludeVpn, vpnType, setVpnType, generating,
    showQrDialog, qrData, selectedDevice, showToken, toggleShowToken,
    handleGenerateToken, handleDeleteDevice, handleShowDeviceQr,
    refetchDevices, closeQrDialog, dialog,
  } = useMobileRegistration();

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <h1 className="text-2xl sm:text-3xl font-semibold text-white mb-2">Mobile Geräte</h1>
        <p className="text-sm text-slate-400">Verwalte deine mobilen BaluHost-Apps</p>
      </div>

      <RegisterDeviceCard
        deviceName={deviceName}
        onDeviceNameChange={setDeviceName}
        tokenValidityDays={tokenValidityDays}
        onValidityChange={setTokenValidityDays}
        includeVpn={includeVpn}
        onIncludeVpnChange={setIncludeVpn}
        vpnType={vpnType}
        onVpnTypeChange={setVpnType}
        availableVpnTypes={availableVpnTypes}
        generating={generating}
        onGenerate={handleGenerateToken}
      />

      <MobileDevicesList
        devices={devices}
        loading={loading}
        isFetching={isFetching}
        isAdmin={isAdmin}
        onRefresh={refetchDevices}
        onShowQr={handleShowDeviceQr}
        onDelete={handleDeleteDevice}
      />

      {showQrDialog && (qrData || selectedDevice) && (
        <QrCodeDialog
          qrData={qrData}
          selectedDevice={selectedDevice}
          isAdmin={isAdmin}
          showToken={showToken}
          onToggleToken={toggleShowToken}
          onClose={closeQrDialog}
        />
      )}
      {dialog}
    </div>
  );
}
```

Note: `RegisterDeviceCard` had `mb-6` on its outer card; `MobileDevicesList`'s
card had none — preserve those exact class strings inside each component (the
register card keeps `... mb-6`, the list card does not) so vertical spacing is
identical. Confirm the moved JSX retained the original outer `className`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/pages/MobileDevicesPage.test.tsx`
Expected: PASS. Then `npx tsc -b`.

- [ ] **Step 5: Commit**

```
git add client/src/pages/MobileDevicesPage.tsx client/src/__tests__/pages/MobileDevicesPage.test.tsx
git commit -m "refactor(mobile): MobileDevicesPage thin orchestrator over mobile-devices/* (#301)"
```

---

### Task 11: Final gates + CLAUDE.md sync

**Files:**
- Modify: `client/src/components/CLAUDE.md` (add `mobile-devices/` row / note under the `device-management/` or a new entry)
- Modify: `client/src/pages/CLAUDE.md` (update the `MobileDevicesPage.tsx` row to mention composition)

- [ ] **Step 1: Run the full gate suite**

Run (from `client/`):
```
npx eslint .
npm run build
npx vitest run
```
Expected: eslint 0 errors; build green; full vitest suite green.

- [ ] **Step 2: Update CLAUDE.md docs**

Add to `components/CLAUDE.md` a `mobile-devices/` entry: "Mobile device registration — `MobileDevicesPage` composes `mobile-devices/*`: `RegisterDeviceCard`, `MobileDevicesList`/`MobileDeviceCard`, `NotificationStatus`, `QrCodeDialog` (→ `NewTokenQrView` / `ExistingDeviceInfoView`) + `mobileDeviceDates` helper; state/handlers in `hooks/useMobileRegistration` (extracted F2/#301)". Update the `MobileDevicesPage.tsx` row in `pages/CLAUDE.md` similarly.

- [ ] **Step 3: Commit**

```
git add client/src/components/CLAUDE.md client/src/pages/CLAUDE.md
git commit -m "docs(mobile): sync CLAUDE.md for mobile-devices decomposition (#301)"
```

## Self-Review

- **Spec coverage:** hook (T2), pure helper incl. all 4 fns (T1), 7 components (T3–T9), orchestrator (T10), gates+docs (T11) — every spec unit has a task.
- **Type consistency:** `UseMobileRegistrationResult` shape identical in T2 and consumed in T10; `MobileExpiry` produced in T1, consumed in T4/T8; `mobileTimeAgo(date, t)` signature consistent T1↔T4; barrel exports (T9) match imports (T10).
- **Placeholder scan:** none; every code step shows full code or an exact verbatim-move instruction with the specific wiring changes named.
- **Locale gotcha:** tests avoid separator-formatted assertions; expiry/time tests compute inputs relative to `Date.now()`.
