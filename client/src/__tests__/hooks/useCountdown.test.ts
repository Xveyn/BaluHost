import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCountdown, formatCountdown } from '../../hooks/useCountdown';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('formatCountdown', () => {
  it('formats < 1h as MM:SS', () => {
    expect(formatCountdown(125)).toBe('02:05');
  });
  it('formats >= 1h as HH:MM:SS', () => {
    expect(formatCountdown(3661)).toBe('01:01:01');
  });
  it('clamps negatives to 00:00', () => {
    expect(formatCountdown(-5)).toBe('00:00');
  });
});

describe('useCountdown', () => {
  it('decrements once per second', () => {
    const { result } = renderHook(({ s }) => useCountdown(s), { initialProps: { s: 120 } });
    expect(result.current).toBe('02:00');
    act(() => { vi.advanceTimersByTime(5000); });
    expect(result.current).toBe('01:55');
  });

  it('re-anchors when seconds prop changes (new poll)', () => {
    const { result, rerender } = renderHook(({ s }) => useCountdown(s), { initialProps: { s: 120 } });
    act(() => { vi.advanceTimersByTime(3000); });
    expect(result.current).toBe('01:57');
    rerender({ s: 600 });   // new poll arrives
    expect(result.current).toBe('10:00');
  });

  it('returns null for null input', () => {
    const { result } = renderHook(() => useCountdown(null));
    expect(result.current).toBeNull();
  });
});
