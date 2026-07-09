import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import type { MigrationJobResponse } from '../../api/migration';

vi.mock('../../api/vcl', () => ({
  getStorageInfo: vi.fn(),
}));
vi.mock('../../api/migration', () => ({
  getMigrationJobs: vi.fn(),
  getMigrationJob: vi.fn(),
}));

import { getStorageInfo } from '../../api/vcl';
import { getMigrationJobs, getMigrationJob } from '../../api/migration';
import { useMigrationData } from '../../hooks/useMigrationData';

const storageMock = vi.mocked(getStorageInfo);
const jobsMock = vi.mocked(getMigrationJobs);
const jobMock = vi.mocked(getMigrationJob);

const storageInfo = { storage_path: '/vcl', blob_count: 3, total_compressed_bytes: 10, disk_available_bytes: 100 } as never;
const running = { id: 5, status: 'running', job_type: 'vcl_to_ssd' } as MigrationJobResponse;
const done = { id: 5, status: 'completed', job_type: 'vcl_to_ssd' } as MigrationJobResponse;

describe('useMigrationData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storageMock.mockResolvedValue(storageInfo);
    jobsMock.mockResolvedValue([]);
    jobMock.mockResolvedValue(running);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns storage info and job history', async () => {
    jobsMock.mockResolvedValue([done]);

    const { result } = renderHook(() => useMigrationData(), { wrapper: createQueryWrapper() });

    await waitFor(() => {
      expect(result.current.storageInfo).not.toBeNull();
      expect(result.current.jobs).toHaveLength(1);
    });
    expect(result.current.storageInfo?.storage_path).toBe('/vcl');
  });

  it('adopts a running job from the list and polls it', async () => {
    jobsMock.mockResolvedValue([running]);

    const { result } = renderHook(() => useMigrationData(), { wrapper: createQueryWrapper() });

    await waitFor(() => {
      expect(result.current.activeJob?.id).toBe(5);
    });
    expect(getMigrationJob).toHaveBeenCalledWith(5);
  });

  it('trackJob() shows the job immediately and polls until terminal', async () => {
    vi.useFakeTimers();

    const { result } = renderHook(() => useMigrationData(), { wrapper: createQueryWrapper() });
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });

    act(() => {
      result.current.trackJob(running);
    });
    // Seeded synchronously — no fetch needed to show it.
    expect(result.current.activeJob?.id).toBe(5);

    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(getMigrationJob).toHaveBeenCalled();

    // Job finishes → poll stops.
    jobMock.mockResolvedValue(done);
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    const callsAfterDone = jobMock.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
    expect(jobMock.mock.calls.length).toBe(callsAfterDone);

    vi.useRealTimers();
  });
});
