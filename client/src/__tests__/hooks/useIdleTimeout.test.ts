import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useIdleTimeout } from '../../hooks/useIdleTimeout';

describe('useIdleTimeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not show warning initially', () => {
    const onLogout = vi.fn();
    const { result } = renderHook(() => useIdleTimeout({ onLogout, enabled: true }));

    expect(result.current.warningVisible).toBe(false);
    expect(result.current.secondsRemaining).toBe(60);
  });

  it('shows warning after idle period (4 min)', () => {
    const onLogout = vi.fn();
    const { result } = renderHook(() => useIdleTimeout({ onLogout, enabled: true }));

    // Advance past the 4-minute idle period
    act(() => { vi.advanceTimersByTime(4 * 60 * 1000); });

    expect(result.current.warningVisible).toBe(true);
  });

  it('calls onLogout after idle + countdown (4min + 60s)', () => {
    const onLogout = vi.fn();
    renderHook(() => useIdleTimeout({ onLogout, enabled: true }));

    // 4 min idle + 60s countdown
    act(() => { vi.advanceTimersByTime(4 * 60 * 1000); });
    act(() => { vi.advanceTimersByTime(60 * 1000); });

    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it('countdown decrements secondsRemaining', () => {
    const onLogout = vi.fn();
    const { result } = renderHook(() => useIdleTimeout({ onLogout, enabled: true }));

    // Enter countdown phase
    act(() => { vi.advanceTimersByTime(4 * 60 * 1000); });

    // Advance 10 seconds into countdown
    act(() => { vi.advanceTimersByTime(10 * 1000); });

    expect(result.current.secondsRemaining).toBe(50);
  });

  it('resetTimer cancels warning and restarts idle period', () => {
    const onLogout = vi.fn();
    const { result } = renderHook(() => useIdleTimeout({ onLogout, enabled: true }));

    // Enter countdown
    act(() => { vi.advanceTimersByTime(4 * 60 * 1000); });
    expect(result.current.warningVisible).toBe(true);

    // User clicks "Stay logged in"
    act(() => { result.current.resetTimer(); });

    expect(result.current.warningVisible).toBe(false);
    expect(result.current.secondsRemaining).toBe(60);
    expect(onLogout).not.toHaveBeenCalled();
  });

  it('does nothing when enabled=false', () => {
    const onLogout = vi.fn();
    const { result } = renderHook(() => useIdleTimeout({ onLogout, enabled: false }));

    act(() => { vi.advanceTimersByTime(10 * 60 * 1000); });

    expect(result.current.warningVisible).toBe(false);
    expect(onLogout).not.toHaveBeenCalled();
  });

  it('cleans up timers on unmount', () => {
    const onLogout = vi.fn();
    const { unmount } = renderHook(() => useIdleTimeout({ onLogout, enabled: true }));

    unmount();

    // Advance past full timeout — should NOT trigger logout
    act(() => { vi.advanceTimersByTime(10 * 60 * 1000); });
    expect(onLogout).not.toHaveBeenCalled();
  });
});

describe('useIdleTimeout — configurable durations', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('uses the 4 min / 60 s defaults when nothing is passed', () => {
    const onLogout = vi.fn();
    const { result } = renderHook(() => useIdleTimeout({ onLogout, enabled: true }));

    act(() => { vi.advanceTimersByTime(4 * 60 * 1000 - 1000); });
    expect(result.current.warningVisible).toBe(false);
    act(() => { vi.advanceTimersByTime(1000); });
    expect(result.current.warningVisible).toBe(true);
  });

  it('waits the configured idle time before warning', () => {
    const onLogout = vi.fn();
    const { result } = renderHook(() =>
      useIdleTimeout({ onLogout, enabled: true, idleMs: 30 * 60 * 1000 }),
    );

    // The old hardcoded 4 minutes must NOT fire any more.
    act(() => { vi.advanceTimersByTime(4 * 60 * 1000); });
    expect(result.current.warningVisible).toBe(false);

    act(() => { vi.advanceTimersByTime(26 * 60 * 1000); });
    expect(result.current.warningVisible).toBe(true);
  });

  it('counts down from the configured warning seconds', () => {
    const onLogout = vi.fn();
    const { result } = renderHook(() =>
      useIdleTimeout({ onLogout, enabled: true, idleMs: 60_000, warningSec: 120 }),
    );

    expect(result.current.secondsRemaining).toBe(120);
    act(() => { vi.advanceTimersByTime(60_000); });
    expect(result.current.secondsRemaining).toBe(120);

    act(() => { vi.advanceTimersByTime(119_000); });
    expect(onLogout).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(1000); });
    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it('picks up changed durations without a remount', () => {
    // The values arrive from the server one render after login, so the hook is
    // always mounted with the defaults first.
    const onLogout = vi.fn();
    const { result, rerender } = renderHook(
      ({ idleMs }) => useIdleTimeout({ onLogout, enabled: true, idleMs }),
      { initialProps: { idleMs: 4 * 60 * 1000 } },
    );

    rerender({ idleMs: 30 * 60 * 1000 });
    act(() => { vi.advanceTimersByTime(4 * 60 * 1000); });

    expect(result.current.warningVisible).toBe(false);
  });
});
