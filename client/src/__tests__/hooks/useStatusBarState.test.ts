import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

vi.mock('../../api/statusBar', () => ({
  getStatusBarState: vi.fn(),
}));

import { getStatusBarState } from '../../api/statusBar';
import { useStatusBarState } from '../../hooks/useStatusBarState';

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});
afterEach(() => vi.useRealTimers());

describe('useStatusBarState', () => {
  it('fetches once on mount and exposes pills', async () => {
    (getStatusBarState as any).mockResolvedValue({
      pills: [{ id: 'power', kind: 'state', tone: 'info', label: 'P', href: '/x' }],
      show_bottom_upload: true,
    });
    const { result } = renderHook(() => useStatusBarState());
    await act(async () => { await Promise.resolve(); });
    expect(result.current.state?.pills).toHaveLength(1);
  });

  it('holds last-known state on a single error', async () => {
    (getStatusBarState as any)
      .mockResolvedValueOnce({ pills: [{ id: 'power', kind: 'state', tone: 'info', label: 'P', href: '/x' }], show_bottom_upload: true })
      .mockRejectedValueOnce(new Error('net'));
    const { result } = renderHook(() => useStatusBarState());
    await act(async () => { await Promise.resolve(); });
    await act(async () => { vi.advanceTimersByTime(10000); await Promise.resolve(); });
    expect(result.current.state?.pills).toHaveLength(1);
  });
});
