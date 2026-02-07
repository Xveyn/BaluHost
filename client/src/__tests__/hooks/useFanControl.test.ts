import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useFanControl } from '../../hooks/useFanControl';

const mockFanStatus = {
  fans: [{ fan_id: 'fan1', name: 'CPU Fan', rpm: 1200, pwm_percent: 50, temperature_celsius: 45, mode: 'auto' as const, is_active: true, min_pwm_percent: 30, max_pwm_percent: 100, emergency_temp_celsius: 90, temp_sensor_id: null, curve_points: [], hysteresis_celsius: 2 }],
  is_dev_mode: true,
  is_using_linux_backend: false,
  permission_status: 'ok',
  backend_available: true,
};

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

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads status and permissions on mount', async () => {
    const { result } = renderHook(() => useFanControl({ refreshInterval: 0 }));

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.status).toEqual(mockFanStatus);
    expect(result.current.permissionStatus).toEqual(mockPermissionStatus);
    expect(result.current.error).toBeNull();
  });

  it('derives isReadOnly from permissionStatus', async () => {
    vi.mocked(getPermissionStatus).mockResolvedValue({
      ...mockPermissionStatus,
      status: 'readonly',
    });

    const { result } = renderHook(() => useFanControl({ refreshInterval: 0 }));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.isReadOnly).toBe(true);
  });

  it('isReadOnly is false when permission is ok', async () => {
    const { result } = renderHook(() => useFanControl({ refreshInterval: 0 }));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.isReadOnly).toBe(false);
  });

  it('pauses auto-refresh when pauseRefresh=true', async () => {
    vi.useFakeTimers();

    const { result, rerender } = renderHook(
      ({ pause }: { pause: boolean }) => useFanControl({ refreshInterval: 5000, pauseRefresh: pause }),
      { initialProps: { pause: false } }
    );

    // Initial load
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(result.current.loading).toBe(false);
    expect(getFanStatus).toHaveBeenCalledTimes(1);

    // Allow one refresh cycle
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(getFanStatus).toHaveBeenCalledTimes(2);

    // Pause
    rerender({ pause: true });

    // Should not refresh while paused
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(getFanStatus).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it('only loads once initially (hasLoadedOnce pattern)', async () => {
    const { result, rerender } = renderHook(() =>
      useFanControl({ refreshInterval: 0 })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(getFanStatus).toHaveBeenCalledTimes(1);

    // Rerender should not trigger another initial load
    rerender();

    await new Promise((r) => setTimeout(r, 50));
    expect(getFanStatus).toHaveBeenCalledTimes(1);
  });

  it('does not fetch when enabled=false', async () => {
    const { result } = renderHook(() =>
      useFanControl({ enabled: false, refreshInterval: 0 })
    );

    await new Promise((r) => setTimeout(r, 50));

    expect(getFanStatus).not.toHaveBeenCalled();
    expect(result.current.status).toBeNull();
  });
});
