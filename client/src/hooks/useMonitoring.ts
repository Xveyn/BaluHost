/**
 * React hook for system monitoring data
 *
 * Provides a unified interface for fetching and polling monitoring metrics.
 */

import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import type {
  TimeRange,
  DataSource,
  CpuSample,
  MemorySample,
  NetworkSample,
  DiskIoSample,
  ProcessSample,
  CurrentCpuResponse,
  CurrentMemoryResponse,
  CurrentNetworkResponse,
} from '../api/monitoring';
import {
  getCpuCurrent,
  getCpuHistory,
  getMemoryCurrent,
  getMemoryHistory,
  getNetworkCurrent,
  getNetworkHistory,
  getDiskIoCurrent,
  getDiskIoHistory,
  getProcessesCurrent,
  getProcessesHistory,
} from '../api/monitoring';

export type MetricType = 'cpu' | 'memory' | 'network' | 'disk-io' | 'processes';

export interface UseMonitoringOptions {
  metricType: MetricType;
  pollInterval?: number; // milliseconds, default 5000
  historyDuration?: TimeRange;
  source?: DataSource;
  enabled?: boolean;
}

export interface UseMonitoringResult<TCurrent, THistory> {
  current: TCurrent | null;
  history: THistory[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  lastUpdated: Date | null;
}

/** First non-null error from a set of query errors, as a user-facing string. */
function firstError(label: string, ...errors: unknown[]): string | null {
  const err = errors.find((e) => e != null);
  return err ? getApiErrorMessage(err, `Failed to fetch ${label} data`) : null;
}

// CPU Hook
export function useCpuMonitoring(
  options: Omit<UseMonitoringOptions, 'metricType'> = {}
): UseMonitoringResult<CurrentCpuResponse, CpuSample> {
  const {
    pollInterval = 5000,
    historyDuration = '1h',
    source = 'auto',
    enabled = true,
  } = options;

  const current = useQuery({
    queryKey: queryKeys.monitoring.cpuCurrent(),
    queryFn: getCpuCurrent,
    refetchInterval: pollInterval,
    enabled,
  });
  const history = useQuery({
    queryKey: queryKeys.monitoring.cpuHistory(historyDuration, source),
    queryFn: () => getCpuHistory(historyDuration, source),
    refetchInterval: pollInterval,
    enabled,
  });

  return {
    current: current.data ?? null,
    history: history.data?.samples ?? [],
    loading: current.isLoading || history.isLoading,
    error: firstError('CPU', current.error, history.error),
    refetch: async () => {
      await Promise.all([current.refetch(), history.refetch()]);
    },
    lastUpdated: current.dataUpdatedAt ? new Date(current.dataUpdatedAt) : null,
  };
}

// Memory Hook
export function useMemoryMonitoring(
  options: Omit<UseMonitoringOptions, 'metricType'> = {}
): UseMonitoringResult<CurrentMemoryResponse, MemorySample> {
  const {
    pollInterval = 5000,
    historyDuration = '1h',
    source = 'auto',
    enabled = true,
  } = options;

  const current = useQuery({
    queryKey: queryKeys.monitoring.memoryCurrent(),
    queryFn: getMemoryCurrent,
    refetchInterval: pollInterval,
    enabled,
  });
  const history = useQuery({
    queryKey: queryKeys.monitoring.memoryHistory(historyDuration, source),
    queryFn: () => getMemoryHistory(historyDuration, source),
    refetchInterval: pollInterval,
    enabled,
  });

  return {
    current: current.data ?? null,
    history: history.data?.samples ?? [],
    loading: current.isLoading || history.isLoading,
    error: firstError('memory', current.error, history.error),
    refetch: async () => {
      await Promise.all([current.refetch(), history.refetch()]);
    },
    lastUpdated: current.dataUpdatedAt ? new Date(current.dataUpdatedAt) : null,
  };
}

// Network Hook
export function useNetworkMonitoring(
  options: Omit<UseMonitoringOptions, 'metricType'> = {}
): UseMonitoringResult<CurrentNetworkResponse, NetworkSample> {
  const {
    pollInterval = 5000,
    historyDuration = '1h',
    source = 'auto',
    enabled = true,
  } = options;

  const current = useQuery({
    queryKey: queryKeys.monitoring.networkCurrent(),
    queryFn: getNetworkCurrent,
    refetchInterval: pollInterval,
    enabled,
  });
  const history = useQuery({
    queryKey: queryKeys.monitoring.networkHistory(historyDuration, source),
    queryFn: () => getNetworkHistory(historyDuration, source),
    refetchInterval: pollInterval,
    enabled,
  });

  return {
    current: current.data ?? null,
    history: history.data?.samples ?? [],
    loading: current.isLoading || history.isLoading,
    error: firstError('network', current.error, history.error),
    refetch: async () => {
      await Promise.all([current.refetch(), history.refetch()]);
    },
    lastUpdated: current.dataUpdatedAt ? new Date(current.dataUpdatedAt) : null,
  };
}

// Disk I/O Hook
export interface UseDiskIoResult {
  disks: Record<string, DiskIoSample | null>;
  history: Record<string, DiskIoSample[]>;
  availableDisks: string[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  lastUpdated: Date | null;
}

export function useDiskIoMonitoring(
  options: Omit<UseMonitoringOptions, 'metricType'> & { diskName?: string } = {}
): UseDiskIoResult {
  const {
    pollInterval = 5000,
    historyDuration = '1h',
    source = 'auto',
    diskName,
    enabled = true,
  } = options;

  const history = useQuery({
    queryKey: queryKeys.monitoring.diskIoHistory(historyDuration, source, diskName),
    queryFn: () => getDiskIoHistory(historyDuration, source, diskName),
    // Poll every 1s until disks are discovered, then back off to pollInterval.
    refetchInterval: (query) =>
      query.state.data?.available_disks?.length ? pollInterval : 1000,
    enabled,
  });

  const fastPoll = !history.data?.available_disks?.length && !history.error;
  const current = useQuery({
    queryKey: queryKeys.monitoring.diskIoCurrent(),
    queryFn: getDiskIoCurrent,
    refetchInterval: fastPoll ? 1000 : pollInterval,
    enabled,
  });

  return {
    disks: current.data?.disks ?? {},
    history: history.data?.disks ?? {},
    availableDisks: history.data?.available_disks ?? [],
    loading: current.isLoading || history.isLoading,
    error: firstError('disk I/O', current.error, history.error),
    refetch: async () => {
      await Promise.all([current.refetch(), history.refetch()]);
    },
    lastUpdated: current.dataUpdatedAt ? new Date(current.dataUpdatedAt) : null,
  };
}

// Process Hook
export interface UseProcessResult {
  processes: Record<string, ProcessSample | null>;
  history: Record<string, ProcessSample[]>;
  crashesDetected: number;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  lastUpdated: Date | null;
}

export function useProcessMonitoring(
  options: Omit<UseMonitoringOptions, 'metricType'> & { processName?: string } = {}
): UseProcessResult {
  const {
    pollInterval = 5000,
    historyDuration = '1h',
    source = 'auto',
    processName,
    enabled = true,
  } = options;

  const current = useQuery({
    queryKey: queryKeys.monitoring.processesCurrent(),
    queryFn: getProcessesCurrent,
    refetchInterval: pollInterval,
    enabled,
  });
  const history = useQuery({
    queryKey: queryKeys.monitoring.processesHistory(historyDuration, source, processName),
    queryFn: () => getProcessesHistory(historyDuration, source, processName),
    refetchInterval: pollInterval,
    enabled,
  });

  return {
    processes: current.data?.processes ?? {},
    history: history.data?.processes ?? {},
    crashesDetected: history.data?.crashes_detected ?? 0,
    loading: current.isLoading || history.isLoading,
    error: firstError('process', current.error, history.error),
    refetch: async () => {
      await Promise.all([current.refetch(), history.refetch()]);
    },
    lastUpdated: current.dataUpdatedAt ? new Date(current.dataUpdatedAt) : null,
  };
}

// Combined monitoring hook for all metrics
export interface UseAllMonitoringResult {
  cpu: UseMonitoringResult<CurrentCpuResponse, CpuSample>;
  memory: UseMonitoringResult<CurrentMemoryResponse, MemorySample>;
  network: UseMonitoringResult<CurrentNetworkResponse, NetworkSample>;
  diskIo: UseDiskIoResult;
  processes: UseProcessResult;
}

export function useAllMonitoring(
  options: { pollInterval?: number; historyDuration?: TimeRange; enabled?: boolean } = {}
): UseAllMonitoringResult {
  const { pollInterval, historyDuration, enabled } = options;

  return {
    cpu: useCpuMonitoring({ pollInterval, historyDuration, enabled }),
    memory: useMemoryMonitoring({ pollInterval, historyDuration, enabled }),
    network: useNetworkMonitoring({ pollInterval, historyDuration, enabled }),
    diskIo: useDiskIoMonitoring({ pollInterval, historyDuration, enabled }),
    processes: useProcessMonitoring({ pollInterval, historyDuration, enabled }),
  };
}
