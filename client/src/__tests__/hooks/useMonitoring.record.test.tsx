import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useDiskIoMonitoring, useProcessMonitoring } from '../../hooks/useMonitoring';
import * as monitoringApi from '../../api/monitoring';

vi.mock('../../api/monitoring');
const api = vi.mocked(monitoringApi);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useDiskIoMonitoring', () => {
  it('maps record-shaped disks/history and availableDisks', async () => {
    api.getDiskIoCurrent.mockResolvedValue({
      disks: { sda: { timestamp: 't0', disk_name: 'sda', read_mbps: 1, write_mbps: 2, read_iops: 3, write_iops: 4 } },
    });
    api.getDiskIoHistory.mockResolvedValue({
      disks: { sda: [] },
      available_disks: ['sda'],
      sample_count: 0,
      source: 'memory',
    });

    const { result } = renderHook(() => useDiskIoMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.availableDisks).toEqual(['sda']);
    expect(result.current.disks.sda?.read_mbps).toBe(1);
    expect(result.current.history.sda).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('fast-polls (~1s) while no disks are available, then backs off', async () => {
    vi.useFakeTimers();
    // Always report no disks so the fast-poll gate stays active.
    api.getDiskIoCurrent.mockResolvedValue({ disks: {} });
    api.getDiskIoHistory.mockResolvedValue({
      disks: {}, available_disks: [], sample_count: 0, source: 'memory',
    });

    renderHook(() => useDiskIoMonitoring({ pollInterval: 5000 }), {
      wrapper: createQueryWrapper(),
    });

    // Flush the initial mount fetch.
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(api.getDiskIoHistory).toHaveBeenCalledTimes(1);

    // After 1s the empty-disks fast-poll fires again (not the 5s pollInterval).
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(api.getDiskIoHistory).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it('does not fetch when enabled is false', async () => {
    api.getDiskIoCurrent.mockResolvedValue({ disks: {} });
    api.getDiskIoHistory.mockResolvedValue({ disks: {}, available_disks: [], sample_count: 0, source: 'memory' });

    const { result } = renderHook(() => useDiskIoMonitoring({ enabled: false }), {
      wrapper: createQueryWrapper(),
    });

    expect(result.current.loading).toBe(false);
    expect(api.getDiskIoCurrent).not.toHaveBeenCalled();
    expect(api.getDiskIoHistory).not.toHaveBeenCalled();
  });
});

describe('useProcessMonitoring', () => {
  it('maps processes/history and crashesDetected', async () => {
    api.getProcessesCurrent.mockResolvedValue({
      processes: { web: { timestamp: 't0', process_name: 'web', pid: 1, cpu_percent: 5, memory_mb: 50, status: 'running', is_alive: true } },
    });
    api.getProcessesHistory.mockResolvedValue({
      processes: { web: [] },
      sample_count: 0,
      source: 'memory',
      crashes_detected: 2,
    });

    const { result } = renderHook(() => useProcessMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.processes.web?.pid).toBe(1);
    expect(result.current.crashesDetected).toBe(2);
  });
});

afterEach(() => {
  vi.useRealTimers();
});
