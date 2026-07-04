import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import {
  useBenchmarkDisks,
  useBenchmark,
  useBenchmarkHistory,
  useBenchmarkProgress,
  useStartBenchmark,
  useCancelBenchmark,
} from '../../hooks/useBenchmark';
import * as benchmarkApi from '../../api/benchmark';
import type {
  DiskInfo,
  BenchmarkResponse,
  BenchmarkProgressResponse,
  BenchmarkListResponse,
} from '../../api/benchmark';

vi.mock('../../api/benchmark');
const api = vi.mocked(benchmarkApi);

const disk: DiskInfo = {
  name: 'sdb',
  size_bytes: 1000,
  size_display: '1 KB',
  is_system_disk: false,
  is_raid_member: false,
  can_benchmark: true,
};

const benchmark: BenchmarkResponse = {
  id: 7,
  disk_name: 'sdb',
  profile: 'quick',
  target_type: 'test_file',
  status: 'completed',
  progress_percent: 100,
  created_at: '2026-01-01T00:00:00Z',
  summary: {},
  test_results: [],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useBenchmarkDisks', () => {
  it('maps the available disks into the result shape', async () => {
    api.getAvailableDisks.mockResolvedValue({ disks: [disk] });
    const { result } = renderHook(() => useBenchmarkDisks(), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.disks).toEqual([disk]);
    expect(result.current.error).toBeNull();
  });

  it('surfaces an error string when the fetch rejects', async () => {
    api.getAvailableDisks.mockRejectedValue(new Error('disks boom'));
    const { result } = renderHook(() => useBenchmarkDisks(), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.error).toBe('disks boom'));
    expect(result.current.disks).toEqual([]);
  });
});

describe('useBenchmark', () => {
  it('does not fetch while the id is null', async () => {
    const { result } = renderHook(() => useBenchmark(null), { wrapper: createQueryWrapper() });

    // Give the query a tick; a disabled query never calls the fn.
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.getBenchmark).not.toHaveBeenCalled();
    expect(result.current.benchmark).toBeNull();
  });

  it('fetches the benchmark once an id is provided', async () => {
    api.getBenchmark.mockResolvedValue(benchmark);
    const { result } = renderHook(() => useBenchmark(7), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.benchmark).toEqual(benchmark));
    expect(api.getBenchmark).toHaveBeenCalledWith(7);
  });
});

describe('useBenchmarkHistory', () => {
  it('maps the paginated history payload', async () => {
    const payload: BenchmarkListResponse = {
      items: [benchmark],
      total: 1,
      page: 1,
      page_size: 5,
      total_pages: 1,
    };
    api.getBenchmarkHistory.mockResolvedValue(payload);
    const { result } = renderHook(() => useBenchmarkHistory(5), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.benchmarks).toEqual([benchmark]);
    expect(result.current.total).toBe(1);
    expect(result.current.totalPages).toBe(1);
    expect(api.getBenchmarkHistory).toHaveBeenCalledWith(1, 5, undefined);
  });
});

describe('useStartBenchmark', () => {
  it('starts a benchmark and returns the response', async () => {
    api.startBenchmark.mockResolvedValue(benchmark);
    const { result } = renderHook(() => useStartBenchmark(), { wrapper: createQueryWrapper() });

    const returned = await result.current.start({ disk_name: 'sdb', profile: 'quick' });
    expect(returned).toEqual(benchmark);
    expect(api.startBenchmark).toHaveBeenCalledWith({ disk_name: 'sdb', profile: 'quick' });
    await waitFor(() => expect(result.current.benchmark).toEqual(benchmark));
  });
});

describe('useCancelBenchmark', () => {
  it('cancels a benchmark by id', async () => {
    api.cancelBenchmark.mockResolvedValue({ message: 'ok', benchmark_id: 7 });
    const { result } = renderHook(() => useCancelBenchmark(), { wrapper: createQueryWrapper() });

    await result.current.cancel(7);
    expect(api.cancelBenchmark).toHaveBeenCalledWith(7);
  });
});

describe('useBenchmarkProgress', () => {
  it('is idle until startPolling and then fetches progress', async () => {
    const running: BenchmarkProgressResponse = { id: 7, status: 'running', progress_percent: 40 };
    api.getBenchmarkProgress.mockResolvedValue(running);

    const { result } = renderHook(() => useBenchmarkProgress(7, { pollingInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    // Disabled until polling starts — no fetch yet.
    expect(api.getBenchmarkProgress).not.toHaveBeenCalled();
    expect(result.current.isPolling).toBe(false);

    act(() => result.current.startPolling());

    await waitFor(() => expect(result.current.progress).toEqual(running));
    expect(result.current.isPolling).toBe(true);
    expect(api.getBenchmarkProgress).toHaveBeenCalledWith(7);
  });
});
