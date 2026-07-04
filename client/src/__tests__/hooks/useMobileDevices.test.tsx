import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useMobileDevices } from '../../hooks/useMobileDevices';
import * as mobileApi from '../../api/mobile';
import type { MobileDevice } from '../../api/mobile';

vi.mock('../../api/mobile');
const api = vi.mocked(mobileApi);

function mobileDevice(o: Partial<MobileDevice>): MobileDevice {
  return {
    id: '1',
    user_id: 1,
    device_name: 'iPhone',
    device_type: 'ios',
    device_model: null,
    os_version: null,
    app_version: null,
    is_active: true,
    last_sync: null,
    expires_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: null,
    ...o,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getMobileDevices.mockResolvedValue([mobileDevice({ id: '1' })]);
});

describe('useMobileDevices', () => {
  it('loads the device list', async () => {
    const { result } = renderHook(() => useMobileDevices(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.devices).toHaveLength(1);
  });

  it('refetch re-requests the devices', async () => {
    const { result } = renderHook(() => useMobileDevices(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    const before = api.getMobileDevices.mock.calls.length;

    await act(async () => {
      await result.current.refetch();
    });
    expect(api.getMobileDevices.mock.calls.length).toBeGreaterThan(before);
  });

  it('defaults to an empty list before data arrives', () => {
    const { result } = renderHook(() => useMobileDevices(), { wrapper: createQueryWrapper() });
    expect(result.current.devices).toEqual([]);
  });
});
