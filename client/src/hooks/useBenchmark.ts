/**
 * React hooks for disk benchmarking.
 *
 * Query-backed (TanStack Query, #299): reads use `useQuery`, the three actions
 * (start/cancel/mark-failed) use `useMutation` invalidating `queryKeys.benchmark.all()`.
 * `useBenchmarkProgress` keeps its imperative `startPolling`/`stopPolling` surface
 * but the poll itself is a query `refetchInterval` that auto-stops on a terminal
 * status — no hand-rolled `setInterval` anymore. All public return shapes are
 * unchanged, so `BenchmarkPanel` is untouched.
 */
import { useState, useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getApiErrorMessage } from '../lib/errorHandling';
import { queryKeys } from '../lib/queryKeys';
import {
  getAvailableDisks,
  getBenchmarkProfiles,
  getBenchmark,
  getBenchmarkProgress,
  getBenchmarkHistory,
  startBenchmark,
  cancelBenchmark,
  markBenchmarkFailed,
  type DiskInfo,
  type BenchmarkProfileConfig,
  type BenchmarkResponse,
  type BenchmarkProgressResponse,
  type BenchmarkStartRequest,
  type BenchmarkStatus,
} from '../api/benchmark';

// ===== Types =====

export interface UseBenchmarkDisksReturn {
  disks: DiskInfo[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export interface UseBenchmarkProfilesReturn {
  profiles: BenchmarkProfileConfig[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export interface UseBenchmarkReturn {
  benchmark: BenchmarkResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export interface UseBenchmarkProgressReturn {
  progress: BenchmarkProgressResponse | null;
  loading: boolean;
  error: string | null;
  isPolling: boolean;
  startPolling: () => void;
  stopPolling: () => void;
}

export interface UseBenchmarkHistoryReturn {
  benchmarks: BenchmarkResponse[];
  total: number;
  page: number;
  totalPages: number;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  setPage: (page: number) => void;
}

export interface UseStartBenchmarkReturn {
  start: (request: BenchmarkStartRequest) => Promise<BenchmarkResponse>;
  loading: boolean;
  error: string | null;
  benchmark: BenchmarkResponse | null;
}

export interface UseCancelBenchmarkReturn {
  cancel: (benchmarkId: number) => Promise<void>;
  loading: boolean;
  error: string | null;
}

export interface UseMarkBenchmarkFailedReturn {
  markFailed: (benchmarkId: number) => Promise<void>;
  loading: boolean;
  error: string | null;
}

// ===== Hooks =====

/**
 * Hook for getting available disks
 */
export function useBenchmarkDisks(): UseBenchmarkDisksReturn {
  const query = useQuery({
    queryKey: queryKeys.benchmark.disks(),
    queryFn: async () => (await getAvailableDisks()).disks,
  });

  return {
    disks: query.data ?? [],
    loading: query.isLoading,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load disks') : null,
    refetch: async () => {
      await query.refetch();
    },
  };
}

/**
 * Hook for getting benchmark profiles
 */
export function useBenchmarkProfiles(): UseBenchmarkProfilesReturn {
  const query = useQuery({
    queryKey: queryKeys.benchmark.profiles(),
    queryFn: async () => (await getBenchmarkProfiles()).profiles,
  });

  return {
    profiles: query.data ?? [],
    loading: query.isLoading,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load profiles') : null,
    refetch: async () => {
      await query.refetch();
    },
  };
}

/**
 * Hook for getting a single benchmark by ID
 */
export function useBenchmark(benchmarkId: number | null): UseBenchmarkReturn {
  const query = useQuery({
    queryKey: queryKeys.benchmark.detail(benchmarkId),
    queryFn: () => getBenchmark(benchmarkId as number),
    enabled: benchmarkId !== null,
  });

  return {
    benchmark: query.data ?? null,
    loading: query.isLoading && benchmarkId !== null,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load benchmark') : null,
    refetch: async () => {
      await query.refetch();
    },
  };
}

/**
 * Hook for polling benchmark progress
 */
export function useBenchmarkProgress(
  benchmarkId: number | null,
  options: { pollingInterval?: number; autoStopOnComplete?: boolean } = {}
): UseBenchmarkProgressReturn {
  const { pollingInterval = 1000, autoStopOnComplete = true } = options;

  // `isPolling` is the imperative on/off the panel drives; it gates the query's
  // `enabled`. The query's function `refetchInterval` auto-stops (returns false)
  // once the benchmark reaches a terminal status when `autoStopOnComplete` is set.
  const [isPolling, setIsPolling] = useState(false);

  const query = useQuery({
    queryKey: queryKeys.benchmark.progress(benchmarkId),
    queryFn: () => getBenchmarkProgress(benchmarkId as number),
    enabled: isPolling && benchmarkId !== null,
    refetchInterval: (q) => {
      if (autoStopOnComplete) {
        const status = q.state.data?.status;
        if (status && isCompleteStatus(status)) return false;
      }
      return pollingInterval;
    },
  });

  const startPolling = useCallback(() => {
    if (benchmarkId === null) return;
    setIsPolling(true);
  }, [benchmarkId]);

  const stopPolling = useCallback(() => {
    setIsPolling(false);
  }, []);

  return {
    progress: query.data ?? null,
    loading: query.isLoading && isPolling,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load progress') : null,
    isPolling,
    startPolling,
    stopPolling,
  };
}

/**
 * Hook for benchmark history with pagination
 */
export function useBenchmarkHistory(
  pageSize: number = 10,
  diskName?: string
): UseBenchmarkHistoryReturn {
  const [page, setPage] = useState(1);

  const query = useQuery({
    queryKey: queryKeys.benchmark.history(page, pageSize, diskName ?? null),
    queryFn: () => getBenchmarkHistory(page, pageSize, diskName),
  });

  return {
    benchmarks: query.data?.items ?? [],
    total: query.data?.total ?? 0,
    page,
    totalPages: query.data?.total_pages ?? 1,
    loading: query.isLoading,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load history') : null,
    refetch: async () => {
      await query.refetch();
    },
    setPage,
  };
}

/**
 * Hook for starting a benchmark
 */
export function useStartBenchmark(): UseStartBenchmarkReturn {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (request: BenchmarkStartRequest) => startBenchmark(request),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.benchmark.all() }),
  });

  const start = useCallback(
    (request: BenchmarkStartRequest) => mutation.mutateAsync(request),
    [mutation],
  );

  return {
    start,
    loading: mutation.isPending,
    error: mutation.isError ? getApiErrorMessage(mutation.error, 'Failed to start benchmark') : null,
    benchmark: mutation.data ?? null,
  };
}

/**
 * Hook for cancelling a benchmark
 */
export function useCancelBenchmark(): UseCancelBenchmarkReturn {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (benchmarkId: number) => cancelBenchmark(benchmarkId),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.benchmark.all() }),
  });

  const cancel = useCallback(
    async (benchmarkId: number) => {
      await mutation.mutateAsync(benchmarkId);
    },
    [mutation],
  );

  return {
    cancel,
    loading: mutation.isPending,
    error: mutation.isError ? getApiErrorMessage(mutation.error, 'Failed to cancel benchmark') : null,
  };
}

/**
 * Hook for marking a benchmark as failed (admin only)
 */
export function useMarkBenchmarkFailed(): UseMarkBenchmarkFailedReturn {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (benchmarkId: number) => markBenchmarkFailed(benchmarkId),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.benchmark.all() }),
  });

  const markFailed = useCallback(
    async (benchmarkId: number) => {
      await mutation.mutateAsync(benchmarkId);
    },
    [mutation],
  );

  return {
    markFailed,
    loading: mutation.isPending,
    error: mutation.isError
      ? getApiErrorMessage(mutation.error, 'Failed to mark benchmark as failed')
      : null,
  };
}

// ===== Helper Functions =====

/**
 * Check if a benchmark status is terminal (complete)
 */
function isCompleteStatus(status: BenchmarkStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled';
}

/**
 * Get status color for styling
 */
export function getBenchmarkStatusColor(status: BenchmarkStatus): string {
  switch (status) {
    case 'completed':
      return 'text-green-600';
    case 'running':
      return 'text-blue-600';
    case 'pending':
      return 'text-yellow-600';
    case 'failed':
      return 'text-red-600';
    case 'cancelled':
      return 'text-gray-600';
    default:
      return 'text-gray-600';
  }
}

/**
 * Get status background color for badges
 */
export function getBenchmarkStatusBgColor(status: BenchmarkStatus): string {
  switch (status) {
    case 'completed':
      return 'bg-green-100 text-green-800';
    case 'running':
      return 'bg-blue-100 text-blue-800';
    case 'pending':
      return 'bg-yellow-100 text-yellow-800';
    case 'failed':
      return 'bg-red-100 text-red-800';
    case 'cancelled':
      return 'bg-gray-100 text-gray-800';
    default:
      return 'bg-gray-100 text-gray-800';
  }
}

/**
 * Format status for display
 */
export function formatBenchmarkStatus(status: BenchmarkStatus): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}
