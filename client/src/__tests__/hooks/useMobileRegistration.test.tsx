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
