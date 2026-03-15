import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useDeviceManagement } from '../../hooks/useDeviceManagement';
import type { Device } from '../../api/devices';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('../../lib/errorHandling', () => ({
  handleApiError: vi.fn(),
}));

const mockDevices: Device[] = [
  { id: '1', name: 'iPhone', type: 'mobile', platform: 'ios', user_id: 1, is_active: true, last_seen: '2026-01-01', created_at: '2026-01-01' },
  { id: '2', name: 'MacBook', type: 'desktop', platform: 'macos', user_id: 1, is_active: true, last_seen: '2026-01-01', created_at: '2026-01-01' },
  { id: '3', name: 'Android', type: 'mobile', platform: 'android', user_id: 1, is_active: false, last_seen: '2025-12-01', created_at: '2025-12-01' },
];

vi.mock('../../api/devices', () => ({
  getAllDevices: vi.fn(),
  updateMobileDeviceName: vi.fn(),
  updateDesktopDeviceName: vi.fn(),
  deleteMobileDevice: vi.fn(),
}));

vi.mock('../../api/sync', () => ({
  createSyncSchedule: vi.fn(),
  listSyncSchedules: vi.fn(),
  disableSyncSchedule: vi.fn(),
  enableSyncSchedule: vi.fn(),
}));

vi.mock('../../api/mobile', () => ({
  generateMobileToken: vi.fn(),
}));

import { getAllDevices, updateMobileDeviceName, updateDesktopDeviceName } from '../../api/devices';
import { listSyncSchedules } from '../../api/sync';
import { generateMobileToken } from '../../api/mobile';

describe('useDeviceManagement', () => {
  beforeEach(() => {
    vi.mocked(getAllDevices).mockResolvedValue(mockDevices);
    vi.mocked(listSyncSchedules).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads devices and computes stats', async () => {
    const { result } = renderHook(() => useDeviceManagement());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.devices).toHaveLength(3);
    expect(result.current.mobileDevices).toHaveLength(2);
    expect(result.current.desktopDevices).toHaveLength(1);
    expect(result.current.stats).toEqual({
      total: 3,
      mobile: 2,
      desktop: 1,
      active: 2,
    });
  });

  it('handleSaveDeviceName calls correct API for mobile', async () => {
    vi.mocked(updateMobileDeviceName).mockResolvedValue(undefined as any);
    const { result } = renderHook(() => useDeviceManagement());

    await waitFor(() => expect(result.current.loading).toBe(false));

    let success: boolean | undefined;
    await act(async () => {
      success = await result.current.handleSaveDeviceName(mockDevices[0], 'New Name');
    });

    expect(updateMobileDeviceName).toHaveBeenCalledWith('1', 'New Name');
    expect(success).toBe(true);
  });

  it('handleSaveDeviceName calls correct API for desktop', async () => {
    vi.mocked(updateDesktopDeviceName).mockResolvedValue(undefined as any);
    const { result } = renderHook(() => useDeviceManagement());

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleSaveDeviceName(mockDevices[1], 'Work MacBook');
    });

    expect(updateDesktopDeviceName).toHaveBeenCalledWith('2', 'Work MacBook');
  });

  it('handleSaveDeviceName rejects empty name', async () => {
    const toast = await import('react-hot-toast');
    const { result } = renderHook(() => useDeviceManagement());

    await waitFor(() => expect(result.current.loading).toBe(false));

    let success: boolean | undefined;
    await act(async () => {
      success = await result.current.handleSaveDeviceName(mockDevices[0], '  ');
    });

    expect(success).toBe(false);
    expect(toast.default.error).toHaveBeenCalled();
  });

  it('handleGenerateToken calls API with correct params', async () => {
    const mockToken = { token: 'abc', qr_code: 'data:image/png;base64,...' };
    vi.mocked(generateMobileToken).mockResolvedValue(mockToken as any);

    const { result } = renderHook(() => useDeviceManagement());
    await waitFor(() => expect(result.current.loading).toBe(false));

    let token: any;
    await act(async () => {
      token = await result.current.handleGenerateToken('My Phone', true, 30, 'wireguard');
    });

    expect(generateMobileToken).toHaveBeenCalledWith(true, 'My Phone', 30, 'wireguard');
    expect(token).toEqual(mockToken);
  });

  it('handleGenerateToken rejects empty name', async () => {
    const toast = await import('react-hot-toast');
    const { result } = renderHook(() => useDeviceManagement());
    await waitFor(() => expect(result.current.loading).toBe(false));

    let token: any;
    await act(async () => {
      token = await result.current.handleGenerateToken('', false, 30);
    });

    expect(token).toBeNull();
    expect(toast.default.error).toHaveBeenCalled();
  });
});
