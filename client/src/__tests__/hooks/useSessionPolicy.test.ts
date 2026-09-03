import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

vi.mock('../../api/pin', () => ({
  getSessionPolicy: vi.fn(),
}));

import { getSessionPolicy } from '../../api/pin';
import { useSessionPolicy } from '../../hooks/useSessionPolicy';
import { DEFAULT_IDLE_MS, DEFAULT_WARNING_SEC } from '../../lib/sessionDefaults';

const mocked = getSessionPolicy as unknown as ReturnType<typeof vi.fn>;

describe('useSessionPolicy', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.mockResolvedValue({ idle_timeout_minutes: 4, idle_warning_seconds: 60 });
  });

  it('starts on the hardcoded fallbacks before the server answers', () => {
    const { result } = renderHook(() => useSessionPolicy(true));

    expect(result.current.idleMs).toBe(DEFAULT_IDLE_MS);
    expect(result.current.warningSec).toBe(DEFAULT_WARNING_SEC);
    expect(result.current.idleEnabled).toBe(true);
  });

  it('applies the configured values', async () => {
    mocked.mockResolvedValue({ idle_timeout_minutes: 30, idle_warning_seconds: 120 });
    const { result } = renderHook(() => useSessionPolicy(true));

    await waitFor(() => expect(result.current.idleMs).toBe(30 * 60 * 1000));
    expect(result.current.warningSec).toBe(120);
    expect(result.current.idleEnabled).toBe(true);
  });

  it('reports the idle logout as disabled at 0 minutes', async () => {
    mocked.mockResolvedValue({ idle_timeout_minutes: 0, idle_warning_seconds: 60 });
    const { result } = renderHook(() => useSessionPolicy(true));

    await waitFor(() => expect(result.current.idleEnabled).toBe(false));
  });

  it('keeps the fallbacks when the request fails', async () => {
    // Losing the setting must never mean losing the idle logout: a broken
    // read silently disabling it would be a security regression.
    mocked.mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useSessionPolicy(true));

    await waitFor(() => expect(mocked).toHaveBeenCalled());
    expect(result.current.idleMs).toBe(DEFAULT_IDLE_MS);
    expect(result.current.warningSec).toBe(DEFAULT_WARNING_SEC);
    expect(result.current.idleEnabled).toBe(true);
  });

  it('asks for nothing while logged out', () => {
    renderHook(() => useSessionPolicy(false));

    expect(mocked).not.toHaveBeenCalled();
  });

  it('fetches once per login, not on every render', async () => {
    const { rerender, result } = renderHook(({ on }) => useSessionPolicy(on), {
      initialProps: { on: true },
    });

    await waitFor(() => expect(mocked).toHaveBeenCalledTimes(1));
    rerender({ on: true });
    rerender({ on: true });

    expect(mocked).toHaveBeenCalledTimes(1);
    expect(result.current.idleEnabled).toBe(true);
  });
});
