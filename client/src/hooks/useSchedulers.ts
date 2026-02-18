import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getSchedulers,
  getSchedulerHistory,
  getAllSchedulerHistory,
  runSchedulerNow,
  toggleScheduler,
  updateSchedulerConfig,
} from '../api/schedulers';
import type {
  SchedulerListResponse,
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
 * Hook for managing all schedulers
 */
export function useSchedulers(options: UseSchedulersOptions = {}): UseSchedulersReturn {
  const { refreshInterval = 30000, enabled = true, pauseRefresh = false } = options;
  const [data, setData] = useState<SchedulerListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const fastPollUntilRef = useRef<number>(0);

  const loadData = useCallback(async () => {
    try {
      const response = await getSchedulers();
      setData(response);
      setError(null);
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || (err instanceof Error ? err.message : 'Failed to load schedulers'));
    }
  }, []);

  // Initial load
  useEffect(() => {
    if (!enabled || hasLoadedOnce) return;

    setLoading(true);
    loadData().finally(() => {
      setLoading(false);
      setHasLoadedOnce(true);
    });
  }, [enabled, hasLoadedOnce, loadData]);

  // Auto-refresh (respects fast-poll mode after Run Now)
  useEffect(() => {
    if (!enabled || !hasLoadedOnce) return;
    if (pauseRefresh) return;

    const tick = () => {
      const now = Date.now();
      const isFastPolling = now < fastPollUntilRef.current;
      const interval = isFastPolling ? FAST_POLL_INTERVAL : refreshInterval;

      if (interval <= 0) return;

      loadData();
      timerId = window.setTimeout(tick, interval);
    };

    const initialInterval =
      Date.now() < fastPollUntilRef.current ? FAST_POLL_INTERVAL : refreshInterval;
    let timerId = window.setTimeout(tick, initialInterval);

    return () => window.clearTimeout(timerId);
  }, [enabled, hasLoadedOnce, refreshInterval, pauseRefresh, loadData]);

  const runNow = useCallback(async (name: string, force: boolean = false): Promise<RunNowResponse> => {
    const response = await runSchedulerNow(name, force);
    // Enable fast polling for 30s so the user sees requested → running → completed
    if (response.success) {
      fastPollUntilRef.current = Date.now() + FAST_POLL_DURATION;
    }
    // Refresh data immediately
    await loadData();
    return response;
  }, [loadData]);

  const toggle = useCallback(async (name: string, toggleEnabled: boolean): Promise<SchedulerToggleResponse> => {
    const response = await toggleScheduler(name, toggleEnabled);
    // Refresh data after toggle
    await loadData();
    return response;
  }, [loadData]);

  const updateConfig = useCallback(async (name: string, config: SchedulerConfigUpdate): Promise<boolean> => {
    try {
      await updateSchedulerConfig(name, config);
      // Refresh data after config update
      await loadData();
      return true;
    } catch {
      return false;
    }
  }, [loadData]);

  return {
    schedulers: data?.schedulers || [],
    totalRunning: data?.total_running || 0,
    totalEnabled: data?.total_enabled || 0,
    loading,
    error,
    refetch: loadData,
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
  setPage: (page: number) => void;
  setStatusFilter: (filter: SchedulerExecStatus | undefined) => void;
}

/**
 * Hook for scheduler execution history
 */
export function useSchedulerHistory(options: UseSchedulerHistoryOptions = {}): UseSchedulerHistoryReturn {
  const {
    schedulerName,
    page: initialPage = 1,
    pageSize = 20,
    statusFilter: initialStatusFilter,
    refreshInterval = 0,
    enabled = true,
  } = options;

  const [page, setPage] = useState(initialPage);
  const [statusFilter, setStatusFilter] = useState<SchedulerExecStatus | undefined>(initialStatusFilter);
  const [history, setHistory] = useState<SchedulerHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      let response: SchedulerHistoryResponse;

      if (schedulerName) {
        response = await getSchedulerHistory(schedulerName, page, pageSize, statusFilter);
      } else {
        response = await getAllSchedulerHistory(page, pageSize, statusFilter, undefined);
      }

      setHistory(response);
      setError(null);
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || (err instanceof Error ? err.message : 'Failed to load history'));
    }
  }, [schedulerName, page, pageSize, statusFilter]);

  // Load on mount and when params change
  useEffect(() => {
    if (!enabled) return;

    setLoading(true);
    loadData().finally(() => {
      setLoading(false);
    });
  }, [enabled, loadData]);

  // Auto-refresh if interval set
  useEffect(() => {
    if (!enabled || refreshInterval <= 0) return;

    const interval = setInterval(loadData, refreshInterval);
    return () => clearInterval(interval);
  }, [enabled, refreshInterval, loadData]);

  return {
    history,
    loading,
    error,
    refetch: loadData,
    setPage,
    setStatusFilter,
  };
}
