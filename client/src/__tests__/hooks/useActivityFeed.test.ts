import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useActivityFeed } from '../../hooks/useActivityFeed';

const mockLogsResponse = {
  dev_mode: true,
  total: 2,
  logs: [
    {
      timestamp: '2026-02-07T11:55:00Z',
      event_type: 'file_access',
      user: 'admin',
      action: 'upload',
      resource: '/docs/report.pdf',
      success: true,
      details: { size_bytes: 4096 },
    },
    {
      timestamp: '2026-02-07T11:50:00Z',
      event_type: 'file_access',
      user: 'user1',
      action: 'download',
      resource: '/images/photo.jpg',
      success: true,
    },
  ],
};

vi.mock('../../api/logging', () => ({
  loggingApi: {
    getFileAccessLogs: vi.fn(),
  },
}));

import { loggingApi } from '../../api/logging';

describe('useActivityFeed', () => {
  beforeEach(() => {
    vi.mocked(loggingApi.getFileAccessLogs).mockReset();
    vi.mocked(loggingApi.getFileAccessLogs).mockResolvedValue(mockLogsResponse);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads and transforms logs into activity items', async () => {
    const { result } = renderHook(() =>
      useActivityFeed({ refreshInterval: 0 })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.activities).toHaveLength(2);
    expect(result.current.activities[0].title).toBe('File Uploaded');
    expect(result.current.activities[0].icon).toBe('upload');
    expect(result.current.activities[1].title).toBe('File Downloaded');
    expect(result.current.error).toBeNull();
  });

  it('uses default options (limit=5, days=1)', async () => {
    renderHook(() => useActivityFeed({ refreshInterval: 0 }));

    await waitFor(() => {
      expect(loggingApi.getFileAccessLogs).toHaveBeenCalled();
    });

    expect(loggingApi.getFileAccessLogs).toHaveBeenCalledWith({ limit: 5, days: 1 });
  });

  it('passes custom options to API', async () => {
    renderHook(() =>
      useActivityFeed({ limit: 10, days: 7, refreshInterval: 0 })
    );

    await waitFor(() => {
      expect(loggingApi.getFileAccessLogs).toHaveBeenCalled();
    });

    expect(loggingApi.getFileAccessLogs).toHaveBeenCalledWith({ limit: 10, days: 7 });
  });

  it('auto-refreshes with interval', async () => {
    vi.useFakeTimers();

    renderHook(() =>
      useActivityFeed({ refreshInterval: 10000 })
    );

    // Initial call
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(loggingApi.getFileAccessLogs).toHaveBeenCalledTimes(1);

    // After 10s
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(loggingApi.getFileAccessLogs).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it('handles errors', async () => {
    vi.mocked(loggingApi.getFileAccessLogs).mockRejectedValue(new Error('Server error'));

    const { result } = renderHook(() =>
      useActivityFeed({ refreshInterval: 0 })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Server error');
    expect(result.current.activities).toEqual([]);
  });
});
