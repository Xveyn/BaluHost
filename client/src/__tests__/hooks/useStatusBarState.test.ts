import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';

vi.mock('../../api/statusBar', () => ({
  getStatusBarState: vi.fn(),
}));

import { getStatusBarState } from '../../api/statusBar';
import type { StatusBarStateResponse } from '../../api/statusBar';
import { useStatusBarState } from '../../hooks/useStatusBarState';

const getState = vi.mocked(getStatusBarState);

const sample = {
  pills: [{ id: 'power', kind: 'state', tone: 'info', label: 'P', href: '/x' }],
  show_bottom_upload: true,
} as unknown as StatusBarStateResponse;

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});
afterEach(() => vi.useRealTimers());

describe('useStatusBarState', () => {
  it('fetches once on mount and exposes pills', async () => {
    getState.mockResolvedValue(sample);

    const { result } = renderHook(() => useStatusBarState(), { wrapper: createQueryWrapper() });
    await act(async () => { await vi.advanceTimersByTimeAsync(5); });

    expect(result.current.state?.pills).toHaveLength(1);
    expect(result.current.stale).toBe(false);
  });

  it('keeps last-known state and flags stale on sustained poll errors', async () => {
    getState.mockResolvedValue(sample);

    const { result } = renderHook(() => useStatusBarState(), { wrapper: createQueryWrapper() });
    await act(async () => { await vi.advanceTimersByTimeAsync(5); });
    expect(result.current.state?.pills).toHaveLength(1);

    // Subsequent polls fail; TanStack retains the last-known data and flips to error.
    getState.mockRejectedValue(new Error('net'));
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });

    expect(result.current.state?.pills).toHaveLength(1); // data retained
    expect(result.current.stale).toBe(true);
  });
});
