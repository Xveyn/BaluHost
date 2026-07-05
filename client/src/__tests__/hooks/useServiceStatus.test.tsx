import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useDebugSnapshot, useServiceControls } from '../../hooks/useServiceStatus';
import * as serviceApi from '../../api/service-status';
import type { AdminDebugSnapshot } from '../../api/service-status';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));
const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('react-hot-toast', () => ({
  default: { success: (...a: unknown[]) => toastSuccess(...a), error: (...a: unknown[]) => toastError(...a) },
}));
vi.mock('../../api/service-status', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/service-status')>();
  return {
    ...actual,
    getDebugSnapshot: vi.fn(),
    restartService: vi.fn(),
    stopService: vi.fn(),
    startService: vi.fn(),
  };
});
const api = vi.mocked(serviceApi);

const snap = (n: number) =>
  ({ services: Array.from({ length: n }, (_, i) => ({ name: `s${i}` })) } as unknown as AdminDebugSnapshot);

beforeEach(() => vi.clearAllMocks());

describe('useDebugSnapshot', () => {
  it('returns the snapshot from getDebugSnapshot', async () => {
    api.getDebugSnapshot.mockResolvedValue(snap(3));
    const { result } = renderHook(() => useDebugSnapshot({ pollInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.snapshot?.services).toHaveLength(3);
    expect(result.current.error).toBeNull();
    expect(result.current.lastUpdated).toBeInstanceOf(Date);
  });

  it('does not fetch when disabled', () => {
    api.getDebugSnapshot.mockResolvedValue(snap(0));
    renderHook(() => useDebugSnapshot({ enabled: false, pollInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });
    expect(api.getDebugSnapshot).not.toHaveBeenCalled();
  });

  it('surfaces an error as a string', async () => {
    api.getDebugSnapshot.mockRejectedValue(new Error('debug boom'));
    const { result } = renderHook(() => useDebugSnapshot({ pollInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.error).toBe('debug boom'));
  });
});

describe('useServiceControls', () => {
  it('restart toasts success and invalidates the snapshot (triggers a refetch)', async () => {
    api.getDebugSnapshot.mockResolvedValue(snap(1));
    api.restartService.mockResolvedValue({ success: true, message: 'ok' } as never);

    const { result } = renderHook(
      () => ({ read: useDebugSnapshot({ pollInterval: 0 }), ctrl: useServiceControls() }),
      { wrapper: createQueryWrapper() },
    );

    await waitFor(() => expect(result.current.read.isLoading).toBe(false));
    expect(api.getDebugSnapshot).toHaveBeenCalledTimes(1);

    await result.current.ctrl.restart('svc-a');

    expect(api.restartService).toHaveBeenCalledWith('svc-a');
    expect(toastSuccess).toHaveBeenCalledTimes(1);
    // onSettled invalidates services.all() → the shared snapshot query refetches.
    await waitFor(() => expect(api.getDebugSnapshot).toHaveBeenCalledTimes(2));
  });

  it('restart toasts the failure message when the action reports failure', async () => {
    api.getDebugSnapshot.mockResolvedValue(snap(1));
    api.restartService.mockResolvedValue({ success: false, message: 'nope' } as never);

    const { result } = renderHook(() => useServiceControls(), { wrapper: createQueryWrapper() });
    await result.current.restart('svc-b');

    expect(toastError).toHaveBeenCalledWith('nope');
    expect(toastSuccess).not.toHaveBeenCalled();
  });
});
