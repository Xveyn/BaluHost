import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useSchedulerHistory } from '../../hooks/useSchedulers';
import * as schedulersApi from '../../api/schedulers';
import type { SchedulerHistoryResponse } from '../../api/schedulers';

vi.mock('../../api/schedulers');
const api = vi.mocked(schedulersApi);

const historyResponse: SchedulerHistoryResponse = {
  executions: [],
  total: 0,
  page: 1,
  page_size: 50,
  total_pages: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getAllSchedulerHistory.mockResolvedValue(historyResponse);
  api.getSchedulerHistory.mockResolvedValue(historyResponse);
});

describe('useSchedulerHistory', () => {
  it('fetches all-scheduler history when no name is given', async () => {
    const { result } = renderHook(() => useSchedulerHistory({ page: 1, pageSize: 50 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.getAllSchedulerHistory).toHaveBeenCalledWith(1, 50, undefined, undefined);
    expect(api.getSchedulerHistory).not.toHaveBeenCalled();
  });

  it('fetches a specific scheduler + status filter when given', async () => {
    const { result } = renderHook(
      () => useSchedulerHistory({ schedulerName: 'backup', page: 2, pageSize: 20, statusFilter: 'failed' }),
      { wrapper: createQueryWrapper() },
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.getSchedulerHistory).toHaveBeenCalledWith('backup', 2, 20, 'failed');
  });

  // Regression guard for the fixed pagination bug: an option change must refetch.
  it('refetches when the page option changes', async () => {
    const { result, rerender } = renderHook(
      ({ page }: { page: number }) => useSchedulerHistory({ page, pageSize: 50 }),
      { initialProps: { page: 1 }, wrapper: createQueryWrapper() },
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.getAllSchedulerHistory).toHaveBeenCalledWith(1, 50, undefined, undefined);

    rerender({ page: 2 });
    await waitFor(() =>
      expect(api.getAllSchedulerHistory).toHaveBeenCalledWith(2, 50, undefined, undefined),
    );
  });

  it('does not fetch when disabled', () => {
    const { result } = renderHook(() => useSchedulerHistory({ enabled: false }), {
      wrapper: createQueryWrapper(),
    });

    expect(result.current.loading).toBe(false);
    expect(api.getAllSchedulerHistory).not.toHaveBeenCalled();
  });
});
