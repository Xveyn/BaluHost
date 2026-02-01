/**
 * React hooks for disk benchmarking
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getAvailableDisks,
  getBenchmarkProfiles,
  getBenchmark,
  getBenchmarkProgress,
  getBenchmarkHistory,
  startBenchmark,
  cancelBenchmark,
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

// ===== Hooks =====

/**
 * Hook for getting available disks
 */
export function useBenchmarkDisks(): UseBenchmarkDisksReturn {
  const [disks, setDisks] = useState<DiskInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDisks = useCallback(async () => {
    try {
      setLoading(true);
      const response = await getAvailableDisks();
      setDisks(response.disks);
      setError(null);
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Failed to load disks';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDisks();
  }, [loadDisks]);

  return { disks, loading, error, refetch: loadDisks };
}

/**
 * Hook for getting benchmark profiles
 */
export function useBenchmarkProfiles(): UseBenchmarkProfilesReturn {
  const [profiles, setProfiles] = useState<BenchmarkProfileConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadProfiles = useCallback(async () => {
    try {
      setLoading(true);
      const response = await getBenchmarkProfiles();
      setProfiles(response.profiles);
      setError(null);
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Failed to load profiles';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles]);

  return { profiles, loading, error, refetch: loadProfiles };
}

/**
 * Hook for getting a single benchmark by ID
 */
export function useBenchmark(benchmarkId: number | null): UseBenchmarkReturn {
  const [benchmark, setBenchmark] = useState<BenchmarkResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadBenchmark = useCallback(async () => {
    if (benchmarkId === null) return;

    try {
      setLoading(true);
      const response = await getBenchmark(benchmarkId);
      setBenchmark(response);
      setError(null);
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Failed to load benchmark';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [benchmarkId]);

  useEffect(() => {
    if (benchmarkId !== null) {
      loadBenchmark();
    } else {
      setBenchmark(null);
    }
  }, [benchmarkId, loadBenchmark]);

  return { benchmark, loading, error, refetch: loadBenchmark };
}

/**
 * Hook for polling benchmark progress
 */
export function useBenchmarkProgress(
  benchmarkId: number | null,
  options: { pollingInterval?: number; autoStopOnComplete?: boolean } = {}
): UseBenchmarkProgressReturn {
  const { pollingInterval = 1000, autoStopOnComplete = true } = options;

  const [progress, setProgress] = useState<BenchmarkProgressResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchProgress = useCallback(async () => {
    if (benchmarkId === null) return;

    try {
      const response = await getBenchmarkProgress(benchmarkId);
      setProgress(response);
      setError(null);

      // Auto-stop polling when benchmark is complete
      if (autoStopOnComplete && isCompleteStatus(response.status)) {
        setIsPolling(false);
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Failed to load progress';
      setError(message);
    }
  }, [benchmarkId, autoStopOnComplete]);

  const startPolling = useCallback(() => {
    if (benchmarkId === null || isPolling) return;

    setIsPolling(true);
    setLoading(true);

    // Initial fetch
    fetchProgress().finally(() => setLoading(false));

    // Start interval
    intervalRef.current = setInterval(fetchProgress, pollingInterval);
  }, [benchmarkId, isPolling, fetchProgress, pollingInterval]);

  const stopPolling = useCallback(() => {
    setIsPolling(false);
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  // Reset when benchmarkId changes
  useEffect(() => {
    stopPolling();
    setProgress(null);
    setError(null);
  }, [benchmarkId, stopPolling]);

  return { progress, loading, error, isPolling, startPolling, stopPolling };
}

/**
 * Hook for benchmark history with pagination
 */
export function useBenchmarkHistory(
  pageSize: number = 10,
  diskName?: string
): UseBenchmarkHistoryReturn {
  const [benchmarks, setBenchmarks] = useState<BenchmarkResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      setLoading(true);
      const response = await getBenchmarkHistory(page, pageSize, diskName);
      setBenchmarks(response.items);
      setTotal(response.total);
      setTotalPages(response.total_pages);
      setError(null);
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Failed to load history';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, diskName]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  return {
    benchmarks,
    total,
    page,
    totalPages,
    loading,
    error,
    refetch: loadHistory,
    setPage,
  };
}

/**
 * Hook for starting a benchmark
 */
export function useStartBenchmark(): UseStartBenchmarkReturn {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [benchmark, setBenchmark] = useState<BenchmarkResponse | null>(null);

  const start = useCallback(async (request: BenchmarkStartRequest) => {
    try {
      setLoading(true);
      setError(null);
      const response = await startBenchmark(request);
      setBenchmark(response);
      return response;
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Failed to start benchmark';
      setError(message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return { start, loading, error, benchmark };
}

/**
 * Hook for cancelling a benchmark
 */
export function useCancelBenchmark(): UseCancelBenchmarkReturn {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cancel = useCallback(async (benchmarkId: number) => {
    try {
      setLoading(true);
      setError(null);
      await cancelBenchmark(benchmarkId);
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Failed to cancel benchmark';
      setError(message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return { cancel, loading, error };
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
