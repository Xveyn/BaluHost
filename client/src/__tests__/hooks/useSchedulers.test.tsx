import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useSchedulers } from '../../hooks/useSchedulers';
import * as schedulersApi from '../../api/schedulers';
import type {
  SchedulerListResponse,
  RunNowResponse,
  SchedulerToggleResponse,
} from '../../api/schedulers';

vi.mock('../../api/schedulers');
const api = vi.mocked(schedulersApi);

const listResponse: SchedulerListResponse = {
  schedulers: [
    {
      name: 'backup',
      display_name: 'Backup',
      description: '',
      is_running: false,
      is_enabled: true,
      interval_seconds: 3600,
      interval_display: 'Every hour',
      last_run_at: null,
      next_run_at: null,
      last_status: null,
      last_error: null,
      last_duration_ms: null,
      config_key: null,
      can_run_manually: true,
      extra_config: null,
      worker_healthy: true,
    },
  ],
  total_running: 0,
  total_enabled: 1,
  worker_healthy: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getSchedulers.mockResolvedValue(listResponse);
});

describe('useSchedulers', () => {
  it('maps the list response into the result shape', async () => {
    const { result } = renderHook(() => useSchedulers({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.schedulers).toHaveLength(1);
    expect(result.current.totalEnabled).toBe(1);
    expect(result.current.workerHealthy).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it('runNow calls the API, returns the response and refetches the list', async () => {
    const runResp: RunNowResponse = {
      success: true,
      message: 'ok',
      execution_id: 1,
      scheduler_name: 'backup',
      status: 'requested',
    };
    api.runSchedulerNow.mockResolvedValue(runResp);

    const { result } = renderHook(() => useSchedulers({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.getSchedulers).toHaveBeenCalledTimes(1);

    let resp: RunNowResponse | undefined;
    await act(async () => {
      resp = await result.current.runNow('backup');
    });

    expect(api.runSchedulerNow).toHaveBeenCalledWith('backup', false);
    expect(resp).toEqual(runResp);
    // onSettled invalidates schedulers.all() → list refetches
    await waitFor(() => expect(api.getSchedulers.mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it('toggle calls the API and returns the response', async () => {
    const toggleResp: SchedulerToggleResponse = {
      success: true,
      scheduler_name: 'backup',
      is_enabled: false,
      message: 'disabled',
    };
    api.toggleScheduler.mockResolvedValue(toggleResp);

    const { result } = renderHook(() => useSchedulers({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    let resp: SchedulerToggleResponse | undefined;
    await act(async () => {
      resp = await result.current.toggle('backup', false);
    });

    expect(api.toggleScheduler).toHaveBeenCalledWith('backup', false);
    expect(resp).toEqual(toggleResp);
  });

  it('updateConfig returns true on success and false on failure', async () => {
    api.updateSchedulerConfig.mockResolvedValueOnce({ success: true, message: 'ok' });

    const { result } = renderHook(() => useSchedulers({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.updateConfig('backup', { is_enabled: true });
    });
    expect(ok).toBe(true);

    api.updateSchedulerConfig.mockRejectedValueOnce(new Error('nope'));
    let ok2: boolean | undefined;
    await act(async () => {
      ok2 = await result.current.updateConfig('backup', { is_enabled: false });
    });
    expect(ok2).toBe(false);
  });

  it('surfaces an error string when the list fetch fails', async () => {
    api.getSchedulers.mockReset();
    api.getSchedulers.mockRejectedValue(new Error('sched boom'));

    const { result } = renderHook(() => useSchedulers({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.error).toBe('sched boom'));
  });
});
