import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createTestQueryClient, createQueryWrapper } from '../helpers/queryClient';
import { queryKeys } from '../../lib/queryKeys';
import { useFanControl } from '../../hooks/useFanControl';

const mockFanStatus = {
  fans: [{ fan_id: 'fan1', name: 'CPU Fan', rpm: 1200, pwm_percent: 50, temperature_celsius: 45, mode: 'auto' as const, is_active: true, min_pwm_percent: 30, max_pwm_percent: 100, emergency_temp_celsius: 90, temp_sensor_id: null, curve_points: [], hysteresis_celsius: 2 }],
  is_dev_mode: true,
  is_using_linux_backend: false,
  permission_status: 'ok',
  backend_available: true,
};

const emptyFanStatus = { ...mockFanStatus, fans: [] };

const mockPermissionStatus = {
  has_write_permission: true,
  status: 'ok',
  message: 'Fan control available',
  suggestions: [],
};

vi.mock('../../api/fan-control', () => ({
  getFanStatus: vi.fn(),
  getPermissionStatus: vi.fn(),
}));

import { getFanStatus, getPermissionStatus } from '../../api/fan-control';

describe('useFanControl', () => {
  beforeEach(() => {
    vi.mocked(getFanStatus).mockReset();
    vi.mocked(getPermissionStatus).mockReset();
    vi.mocked(getFanStatus).mockResolvedValue(mockFanStatus);
    vi.mocked(getPermissionStatus).mockResolvedValue(mockPermissionStatus);
  });

  it('loads status and permissions on mount', async () => {
    const { result } = renderHook(() => useFanControl({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.status).toEqual(mockFanStatus);
    expect(result.current.permissionStatus).toEqual(mockPermissionStatus);
    expect(result.current.error).toBeNull();
  });

  it('derives isReadOnly from permissionStatus', async () => {
    vi.mocked(getPermissionStatus).mockResolvedValue({ ...mockPermissionStatus, status: 'readonly' });

    const { result } = renderHook(() => useFanControl({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.isReadOnly).toBe(true);
  });

  it('isReadOnly is false when permission is ok', async () => {
    const { result } = renderHook(() => useFanControl({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.isReadOnly).toBe(false);
  });

  it('does not fetch when enabled=false', async () => {
    const { result } = renderHook(() => useFanControl({ enabled: false, refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });

    await new Promise((r) => setTimeout(r, 20));
    expect(getFanStatus).not.toHaveBeenCalled();
    expect(result.current.status).toBeNull();
  });

  it('masks a transient empty fan list with the last non-empty status', async () => {
    const client = createTestQueryClient();
    const { result } = renderHook(() => useFanControl({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(client),
    });

    await waitFor(() => expect(result.current.status).toEqual(mockFanStatus));

    // A later poll returns no fans — the guard keeps the last non-empty snapshot.
    vi.mocked(getFanStatus).mockResolvedValue(emptyFanStatus);
    await act(async () => {
      await client.refetchQueries({ queryKey: queryKeys.fans.control() });
    });

    expect(result.current.status?.fans).toHaveLength(1);
  });
});
