import { useCallback, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import {
  getSchedulers,
  getSchedulerHistory,
  getAllSchedulerHistory,
  runSchedulerNow,
  toggleScheduler,
  updateSchedulerConfig,
} from '../api/schedulers';
import type {
  SchedulerStatus,
  SchedulerHistoryResponse,
  SchedulerExecStatus,
  RunNowResponse,
  SchedulerToggleResponse,
  SchedulerConfigUpdate,
} from '../api/schedulers';

// Hook options
interface UseSchedulersOptions {
  refreshInterval?: number;
  enabled?: boolean;
  pauseRefresh?: boolean;
}

interface UseSchedulersReturn {
  schedulers: SchedulerStatus[];
  totalRunning: number;
  totalEnabled: number;
  workerHealthy: boolean | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  runNow: (name: string, force?: boolean) => Promise<RunNowResponse>;
  toggle: (name: string, enabled: boolean) => Promise<SchedulerToggleResponse>;
  updateConfig: (name: string, config: SchedulerConfigUpdate) => Promise<boolean>;
}

// Fast polling duration (ms) after a "Run Now" action
const FAST_POLL_DURATION = 30_000;
const FAST_POLL_INTERVAL = 3_000;

/**
 * Hook for managing all schedulers. Reads are TanStack Query backed; the three
 * mutations (runNow/toggle/updateConfig) go through useMutation and invalidate
 * the schedulers domain (list + history) on settle. Public shape unchanged.
 */
export function useSchedulers(options: UseSchedulersOptions = {}): UseSchedulersReturn {
  const { refreshInterval = 30000, enabled = true, pauseRefresh = false } = options;
  const queryClient = useQueryClient();

  // After a Run Now we poll fast (3s) for 30s so the user sees the execution go
  // requested → running → completed, then fall back to the normal interval.
  const fastPollUntilRef = useRef<number>(0);

  const query = useQuery({
    queryKey: queryKeys.schedulers.list(),
    queryFn: getSchedulers,
    enabled,
    refetchInterval: pauseRefresh
      ? false
      : () => (Date.now() < fastPollUntilRef.current ? FAST_POLL_INTERVAL : refreshInterval),
  });

  const invalidate = useCallback(
    () => queryClient.invalidateQueries({ queryKey: queryKeys.schedulers.all() }),
    [queryClient],
  );

  const runNowMutation = useMutation({
    mutationFn: ({ name, force }: { name: string; force: boolean }) => runSchedulerNow(name, force),
    onSuccess: (response) => {
      if (response.success) {
        fastPollUntilRef.current = Date.now() + FAST_POLL_DURATION;
      }
    },
    // Refresh immediately (and await, so callers see fresh data on resolve).
    onSettled: () => invalidate(),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ name, enabled: toggleEnabled }: { name: string; enabled: boolean }) =>
      toggleScheduler(name, toggleEnabled),
    onSettled: () => invalidate(),
  });

  const updateConfigMutation = useMutation({
    mutationFn: ({ name, config }: { name: string; config: SchedulerConfigUpdate }) =>
      updateSchedulerConfig(name, config),
    onSettled: () => invalidate(),
  });

  const runNow = useCallback(
    (name: string, force = false): Promise<RunNowResponse> =>
      runNowMutation.mutateAsync({ name, force }),
    [runNowMutation],
  );

  const toggle = useCallback(
    (name: string, toggleEnabled: boolean): Promise<SchedulerToggleResponse> =>
      toggleMutation.mutateAsync({ name, enabled: toggleEnabled }),
    [toggleMutation],
  );

  const updateConfig = useCallback(
    async (name: string, config: SchedulerConfigUpdate): Promise<boolean> => {
      try {
        await updateConfigMutation.mutateAsync({ name, config });
        return true;
      } catch {
        return false;
      }
    },
    [updateConfigMutation],
  );

  return {
    schedulers: query.data?.schedulers ?? [],
    totalRunning: query.data?.total_running ?? 0,
    totalEnabled: query.data?.total_enabled ?? 0,
    workerHealthy: query.data?.worker_healthy ?? null,
    loading: query.isLoading,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load schedulers') : null,
    refetch: async () => {
      await query.refetch();
    },
    runNow,
    toggle,
    updateConfig,
  };
}

// History hook options
interface UseSchedulerHistoryOptions {
  schedulerName?: string;
  page?: number;
  pageSize?: number;
  statusFilter?: SchedulerExecStatus;
  refreshInterval?: number;
  enabled?: boolean;
}

interface UseSchedulerHistoryReturn {
  history: SchedulerHistoryResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * Hook for scheduler execution history. Fully options-driven — page, pageSize,
 * statusFilter and schedulerName are part of the query key, so changing any of
 * them refetches. (Previously these seeded internal state once and later option
 * changes were ignored, so consumer-driven pagination/filtering never refetched.)
 */
export function useSchedulerHistory(options: UseSchedulerHistoryOptions = {}): UseSchedulerHistoryReturn {
  const {
    schedulerName,
    page = 1,
    pageSize = 20,
    statusFilter,
    refreshInterval = 0,
    enabled = true,
  } = options;

  const query = useQuery({
    queryKey: queryKeys.schedulers.history(
      schedulerName ?? null,
      page,
      pageSize,
      statusFilter ?? null,
    ),
    queryFn: () =>
      schedulerName
        ? getSchedulerHistory(schedulerName, page, pageSize, statusFilter)
        : getAllSchedulerHistory(page, pageSize, statusFilter, undefined),
    enabled,
    refetchInterval: refreshInterval > 0 ? refreshInterval : false,
  });

  return {
    history: query.data ?? null,
    loading: query.isLoading,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load history') : null,
    refetch: async () => {
      await query.refetch();
    },
  };
}
