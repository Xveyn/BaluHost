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
