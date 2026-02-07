import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useAsyncData } from '../../hooks/useAsyncData';

describe('useAsyncData', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches data successfully', async () => {
    const fetcher = vi.fn().mockResolvedValue({ id: 1, name: 'test' });
    const { result } = renderHook(() => useAsyncData(fetcher));

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual({ id: 1, name: 'test' });
    expect(result.current.error).toBeNull();
    expect(fetcher).toHaveBeenCalledOnce();
  });

  it('handles fetch errors', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('Network error'));
    const { result } = renderHook(() => useAsyncData(fetcher));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe('Network error');
  });

  it('handles non-Error rejections', async () => {
    const fetcher = vi.fn().mockRejectedValue('string error');
    const { result } = renderHook(() => useAsyncData(fetcher));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('An error occurred');
  });

  it('starts with loading true', () => {
    const fetcher = vi.fn().mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAsyncData(fetcher));
    expect(result.current.loading).toBe(true);
  });

  it('refetch updates data', async () => {
    let callCount = 0;
    const fetcher = vi.fn().mockImplementation(() => {
      callCount++;
      return Promise.resolve({ count: callCount });
    });

    const { result } = renderHook(() => useAsyncData(fetcher));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual({ count: 1 });

    await act(async () => {
      result.current.refetch();
    });

    await waitFor(() => {
      expect(result.current.data).toEqual({ count: 2 });
    });
  });

  it('does not fetch when enabled=false', async () => {
    const fetcher = vi.fn().mockResolvedValue('data');
    const { result } = renderHook(() =>
      useAsyncData(fetcher, { enabled: false })
    );

    // Should immediately be not loading
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('auto-refreshes with refreshInterval', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockResolvedValue('data');

    renderHook(() =>
      useAsyncData(fetcher, { refreshInterval: 5000 })
    );

    // Initial call
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    // After 5s, should call again
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it('cleans up interval on unmount', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockResolvedValue('data');

    const { unmount } = renderHook(() =>
      useAsyncData(fetcher, { refreshInterval: 5000 })
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    unmount();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    // Should not have been called again after unmount
    expect(fetcher).toHaveBeenCalledTimes(1);

    vi.useRealTimers();
  });
});
