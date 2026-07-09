import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import type { CloudConnection, CloudImportJob } from '../../api/cloud-import';

vi.mock('../../api/cloud-import', () => ({
  getConnections: vi.fn(),
  getJobs: vi.fn(),
}));

import { getConnections, getJobs } from '../../api/cloud-import';
import { useCloudImportData } from '../../hooks/useCloudImportData';

const connectionsMock = vi.mocked(getConnections);
const jobsMock = vi.mocked(getJobs);

const conn = { id: 1, display_name: 'Drive' } as CloudConnection;
const runningJob = { id: 7, status: 'running' } as CloudImportJob;
const doneJob = { id: 7, status: 'completed' } as CloudImportJob;

describe('useCloudImportData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    connectionsMock.mockResolvedValue([conn]);
    jobsMock.mockResolvedValue([doneJob]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns connections and jobs', async () => {
    const { result } = renderHook(() => useCloudImportData(), { wrapper: createQueryWrapper() });

    await waitFor(() => {
      expect(result.current.connections).toHaveLength(1);
      expect(result.current.jobs).toHaveLength(1);
    });
    expect(result.current.connections[0].display_name).toBe('Drive');
  });

  it('polls jobs every 3s while a job is running or pending', async () => {
    vi.useFakeTimers();
    jobsMock.mockResolvedValue([runningJob]);

    renderHook(() => useCloudImportData(), { wrapper: createQueryWrapper() });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(getJobs).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(getJobs).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it('does not poll jobs once all jobs are terminal', async () => {
    vi.useFakeTimers();
    jobsMock.mockResolvedValue([doneJob]);

    renderHook(() => useCloudImportData(), { wrapper: createQueryWrapper() });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(getJobs).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(getJobs).toHaveBeenCalledTimes(1);

    vi.useRealTimers();
  });

  it('refetch() re-requests both endpoints', async () => {
    const { result } = renderHook(() => useCloudImportData(), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.connections).toHaveLength(1));
    expect(getConnections).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.refetch();
    });

    expect(getConnections).toHaveBeenCalledTimes(2);
    expect(getJobs).toHaveBeenCalledTimes(2);
  });
});
