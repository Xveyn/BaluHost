import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePowerActions } from '../../hooks/usePowerActions';

const localApiMock = vi.hoisted(() => ({
  shutdown: vi.fn(),
  restart: vi.fn(),
  isAvailable: vi.fn(),
}));
vi.mock('../../lib/localApi', () => ({ localApi: localApiMock }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const reloadMock = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  localApiMock.shutdown.mockReset();
  localApiMock.restart.mockReset();
  localApiMock.isAvailable.mockReset();
  reloadMock.mockReset();
  // jsdom implementiert reload nicht — ersetzen
  Object.defineProperty(window, 'location', {
    value: { ...window.location, reload: reloadMock },
    writable: true,
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('usePowerActions', () => {
  it('shutdown: pending → nach (eta+1)s logout und pending zurückgesetzt', async () => {
    localApiMock.shutdown.mockResolvedValue({ eta_seconds: 3 });
    const logout = vi.fn();
    const { result } = renderHook(() => usePowerActions(logout));
    await act(() => result.current.onShutdown());
    expect(result.current.pendingAction).toBe('shutdown');
    await act(() => vi.advanceTimersByTimeAsync(4000));
    expect(logout).toHaveBeenCalledTimes(1);
    expect(result.current.pendingAction).toBeNull();
  });

  it('shutdown-Fehler: Fallback-Timeout 2s → logout', async () => {
    localApiMock.shutdown.mockRejectedValue(new Error('nope'));
    const logout = vi.fn();
    const { result } = renderHook(() => usePowerActions(logout));
    await act(() => result.current.onShutdown());
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('restart: pollt bis Server verfügbar, dann reload', async () => {
    localApiMock.restart.mockResolvedValue(undefined);
    localApiMock.isAvailable.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    const { result } = renderHook(() => usePowerActions(vi.fn()));
    await act(() => result.current.onRestart());
    expect(result.current.pendingAction).toBe('restart');
    await act(() => vi.advanceTimersByTimeAsync(2000)); // Poll 1: false
    expect(reloadMock).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(2000)); // Poll 2: true
    expect(reloadMock).toHaveBeenCalledTimes(1);
    expect(result.current.pendingAction).toBeNull();
  });

  it('restart: nach 60s ohne Server → logout', async () => {
    localApiMock.restart.mockResolvedValue(undefined);
    localApiMock.isAvailable.mockResolvedValue(false);
    const logout = vi.fn();
    const { result } = renderHook(() => usePowerActions(logout));
    await act(() => result.current.onRestart());
    await act(() => vi.advanceTimersByTimeAsync(62000));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('Cleanup: Unmount während des Pollings stoppt Intervall und Timeouts', async () => {
    localApiMock.restart.mockResolvedValue(undefined);
    localApiMock.isAvailable.mockResolvedValue(false);
    const logout = vi.fn();
    const { result, unmount } = renderHook(() => usePowerActions(logout));
    await act(() => result.current.onRestart());
    await act(() => vi.advanceTimersByTimeAsync(2000));
    const callsBefore = localApiMock.isAvailable.mock.calls.length;
    unmount();
    await act(() => vi.advanceTimersByTimeAsync(20000));
    expect(localApiMock.isAvailable.mock.calls.length).toBe(callsBefore);
    expect(logout).not.toHaveBeenCalled();
    expect(reloadMock).not.toHaveBeenCalled();
  });
});
