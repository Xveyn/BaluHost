import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useQuery } from '@tanstack/react-query';
import { createQueryWrapper } from '../helpers/queryClient';
import { queryKeys } from '../../lib/queryKeys';

vi.mock('../../api/system', () => ({
  getSystemMode: vi.fn(),
}));
vi.mock('../../api/smart', () => ({
  getSmartMode: vi.fn(),
  toggleSmartMode: vi.fn(),
}));

import { getSystemMode } from '../../api/system';
import { getSmartMode, toggleSmartMode } from '../../api/smart';
import { useSmartMode } from '../../hooks/useSmartMode';

const sysMode = vi.mocked(getSystemMode);
const smartMode = vi.mocked(getSmartMode);
const toggle = vi.mocked(toggleSmartMode);

describe('useSmartMode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sysMode.mockResolvedValue({ dev_mode: true } as Awaited<ReturnType<typeof getSystemMode>>);
    smartMode.mockResolvedValue({ mode: 'mock' });
    toggle.mockResolvedValue({ mode: 'real', message: 'switched' });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('exposes the smart mode in dev mode', async () => {
    const { result } = renderHook(() => useSmartMode(), { wrapper: createQueryWrapper() });

    await waitFor(() => {
      expect(result.current.isDevMode).toBe(true);
      expect(result.current.smartMode).toBe('mock');
    });
  });

  it('does not fetch smart mode outside dev mode', async () => {
    sysMode.mockResolvedValue({ dev_mode: false } as Awaited<ReturnType<typeof getSystemMode>>);

    const { result } = renderHook(() => useSmartMode(), { wrapper: createQueryWrapper() });

    await waitFor(() => {
      expect(result.current.isDevMode).toBe(false);
    });
    // Give any (incorrect) smart-mode fetch a chance to fire.
    await new Promise((r) => setTimeout(r, 20));

    expect(getSmartMode).not.toHaveBeenCalled();
    expect(result.current.smartMode).toBeNull();
  });

  it('toggle() flips the exposed mode via the shared cache', async () => {
    const { result } = renderHook(() => useSmartMode(), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.smartMode).toBe('mock'));

    await act(async () => {
      await result.current.toggle();
    });

    expect(toggleSmartMode).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(result.current.smartMode).toBe('real'));
  });

  it('shares queryKeys.smart.mode() — one fetch feeds the hook and a co-mounted reader', async () => {
    const { result } = renderHook(
      () => ({
        hook: useSmartMode(),
        reader: useQuery({ queryKey: queryKeys.smart.mode(), queryFn: getSmartMode }),
      }),
      { wrapper: createQueryWrapper() }
    );

    await waitFor(() => {
      expect(result.current.hook.smartMode).toBe('mock');
      expect(result.current.reader.data?.mode).toBe('mock');
    });

    expect(getSmartMode).toHaveBeenCalledTimes(1);
  });
});
