import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useServicesSummary } from '../../hooks/useServicesSummary';
import * as serviceApi from '../../api/service-status';
import { ServiceState, type ServiceStatus, type AdminDebugSnapshot } from '../../api/service-status';

vi.mock('../../api/service-status', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/service-status')>();
  return { ...actual, getDebugSnapshot: vi.fn() };
});
const api = vi.mocked(serviceApi);

function service(state: ServiceState): ServiceStatus {
  return {
    name: 's',
    display_name: 'S',
    state,
    started_at: null,
    uptime_seconds: null,
    sample_count: null,
    error_count: 0,
    last_error: null,
    last_error_at: null,
    config_enabled: true,
    interval_seconds: null,
    restartable: false,
  };
}

function snapshot(services: ServiceStatus[]): AdminDebugSnapshot {
  return { services } as unknown as AdminDebugSnapshot;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useServicesSummary', () => {
  it('derives the summary from the service list', async () => {
    api.getDebugSnapshot.mockResolvedValue(
      snapshot([
        service(ServiceState.RUNNING),
        service(ServiceState.RUNNING),
        service(ServiceState.STOPPED),
        service(ServiceState.ERROR),
        service(ServiceState.DISABLED),
      ]),
    );

    const { result } = renderHook(() => useServicesSummary({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.summary).toEqual({
      running: 2,
      stopped: 1,
      error: 1,
      disabled: 1,
      total: 5,
    });
    expect(result.current.error).toBeNull();
  });

  it('does not fetch when disabled', () => {
    api.getDebugSnapshot.mockResolvedValue(snapshot([]));

    const { result } = renderHook(() => useServicesSummary({ enabled: false }), {
      wrapper: createQueryWrapper(),
    });

    expect(result.current.loading).toBe(false);
    expect(api.getDebugSnapshot).not.toHaveBeenCalled();
  });

  it('surfaces an error as a string', async () => {
    api.getDebugSnapshot.mockRejectedValue(new Error('services boom'));

    const { result } = renderHook(() => useServicesSummary({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.error).toBe('services boom'));
  });
});
