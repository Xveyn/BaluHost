import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePresenceHeartbeat } from '../../hooks/usePresenceHeartbeat';
import { sendPresenceHeartbeat } from '../../api/sleep';

vi.mock('../../api/sleep', () => ({
  sendPresenceHeartbeat: vi.fn().mockResolvedValue({
    present: true,
    enabled: true,
    mode: 'active',
    heartbeat_interval_seconds: 45,
    timeout_minutes: 3,
  }),
}));

const mockedSend = vi.mocked(sendPresenceHeartbeat);

function setVisibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', {
    value: state,
    configurable: true,
  });
}

async function flushAsync() {
  // let pending promise callbacks run
  await act(async () => { await Promise.resolve(); });
}

describe('usePresenceHeartbeat', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    sessionStorage.clear();
    setVisibility('visible');
    mockedSend.mockClear();
    mockedSend.mockResolvedValue({
      present: true,
      enabled: true,
      mode: 'active',
      heartbeat_interval_seconds: 45,
      timeout_minutes: 3,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('sends an immediate heartbeat on mount when visible', async () => {
    renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(1);
    const arg = mockedSend.mock.calls[0][0];
    expect(arg.client_type).toBe('web');
    expect(arg.client_id.length).toBeGreaterThanOrEqual(8);
  });

  it('sends heartbeats on the interval while visible', async () => {
    renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    await act(async () => { vi.advanceTimersByTime(45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(2);
  });

  it('skips heartbeats while hidden in active mode', async () => {
    renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    setVisibility('hidden');
    await act(async () => { vi.advanceTimersByTime(3 * 45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(1); // only the initial beat
  });

  it('keeps sending while hidden in session mode', async () => {
    mockedSend.mockResolvedValue({
      present: true,
      enabled: true,
      mode: 'session',
      heartbeat_interval_seconds: 45,
      timeout_minutes: 3,
    });
    renderHook(() => usePresenceHeartbeat());
    await flushAsync(); // initial beat -> learns mode 'session'
    setVisibility('hidden');
    await act(async () => { vi.advanceTimersByTime(45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(2);
  });

  it('sends immediately when the tab becomes visible again', async () => {
    renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    setVisibility('hidden');
    await act(async () => { vi.advanceTimersByTime(45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(1);

    setVisibility('visible');
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(2);
  });

  it('stops on unmount', async () => {
    const { unmount } = renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    unmount();
    await act(async () => { vi.advanceTimersByTime(10 * 45_000); });
    expect(mockedSend).toHaveBeenCalledTimes(1);
  });

  it('swallows API errors silently', async () => {
    mockedSend.mockRejectedValueOnce(new Error('network down'));
    renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    // no throw; next interval still fires
    await act(async () => { vi.advanceTimersByTime(45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(2);
  });

  it('reuses the same client_id across beats (sessionStorage)', async () => {
    renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    await act(async () => { vi.advanceTimersByTime(45_000); });
    await flushAsync();
    const ids = mockedSend.mock.calls.map((c) => c[0].client_id);
    expect(new Set(ids).size).toBe(1);
  });

  it('skips heartbeats while paused (session mode, visible)', async () => {
    mockedSend.mockResolvedValue({
      present: true,
      enabled: true,
      mode: 'session',
      heartbeat_interval_seconds: 45,
      timeout_minutes: 3,
    });
    const { rerender } = renderHook(
      ({ paused }) => usePresenceHeartbeat({ paused }),
      { initialProps: { paused: false } },
    );
    await flushAsync(); // initial beat -> learns mode 'session'
    expect(mockedSend).toHaveBeenCalledTimes(1);

    rerender({ paused: true });
    await act(async () => { vi.advanceTimersByTime(3 * 45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(1); // no new beats while paused
  });

  it('resumes heartbeats after un-pausing', async () => {
    const { rerender } = renderHook(
      ({ paused }) => usePresenceHeartbeat({ paused }),
      { initialProps: { paused: true } },
    );
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(0); // paused from mount: even initial beat skipped

    rerender({ paused: false });
    await act(async () => { vi.advanceTimersByTime(45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(1);
  });

  it('sends nothing when disabled', async () => {
    renderHook(() => usePresenceHeartbeat({ enabled: false }));
    await flushAsync();
    await act(async () => { vi.advanceTimersByTime(3 * 45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(0);
  });
});
