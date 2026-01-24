/**
 * React hook for system monitoring data
 *
 * Provides a unified interface for fetching and polling monitoring metrics.
 */

import { useState, useEffect, useCallback } from 'react';
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

  const [current, setCurrent] = useState<CurrentCpuResponse | null>(null);
  const [history, setHistory] = useState<CpuSample[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [currentData, historyData] = await Promise.all([
        getCpuCurrent(),
        getCpuHistory(historyDuration, source),
      ]);
      setCurrent(currentData);
      setHistory(historyData.samples);
      setError(null);
      setLastUpdated(new Date());
    } catch (err: any) {
      setError(err.message || 'Failed to fetch CPU data');
    } finally {
      setLoading(false);
    }
  }, [historyDuration, source]);

  useEffect(() => {
    if (!enabled) return;

    fetchData();
    const interval = setInterval(fetchData, pollInterval);
    return () => clearInterval(interval);
  }, [fetchData, pollInterval, enabled]);

  return { current, history, loading, error, refetch: fetchData, lastUpdated };
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

  const [current, setCurrent] = useState<CurrentMemoryResponse | null>(null);
  const [history, setHistory] = useState<MemorySample[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [currentData, historyData] = await Promise.all([
        getMemoryCurrent(),
        getMemoryHistory(historyDuration, source),
      ]);
      setCurrent(currentData);
      setHistory(historyData.samples);
      setError(null);
      setLastUpdated(new Date());
    } catch (err: any) {
      setError(err.message || 'Failed to fetch memory data');
    } finally {
      setLoading(false);
    }
  }, [historyDuration, source]);

  useEffect(() => {
    if (!enabled) return;

    fetchData();
    const interval = setInterval(fetchData, pollInterval);
    return () => clearInterval(interval);
  }, [fetchData, pollInterval, enabled]);

  return { current, history, loading, error, refetch: fetchData, lastUpdated };
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

  const [current, setCurrent] = useState<CurrentNetworkResponse | null>(null);
  const [history, setHistory] = useState<NetworkSample[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [currentData, historyData] = await Promise.all([
        getNetworkCurrent(),
        getNetworkHistory(historyDuration, source),
      ]);
      setCurrent(currentData);
      setHistory(historyData.samples);
      setError(null);
      setLastUpdated(new Date());
    } catch (err: any) {
      setError(err.message || 'Failed to fetch network data');
    } finally {
      setLoading(false);
    }
  }, [historyDuration, source]);

  useEffect(() => {
    if (!enabled) return;

    fetchData();
    const interval = setInterval(fetchData, pollInterval);
    return () => clearInterval(interval);
  }, [fetchData, pollInterval, enabled]);

  return { current, history, loading, error, refetch: fetchData, lastUpdated };
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

  const [disks, setDisks] = useState<Record<string, DiskIoSample | null>>({});
  const [history, setHistory] = useState<Record<string, DiskIoSample[]>>({});
  const [availableDisks, setAvailableDisks] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [currentData, historyData] = await Promise.all([
        getDiskIoCurrent(),
        getDiskIoHistory(historyDuration, source, diskName),
      ]);
      setDisks(currentData.disks);
      setHistory(historyData.disks);
      setAvailableDisks(historyData.available_disks);
      setError(null);
      setLastUpdated(new Date());
    } catch (err: any) {
      setError(err.message || 'Failed to fetch disk I/O data');
    } finally {
      setLoading(false);
    }
  }, [historyDuration, source, diskName]);

  useEffect(() => {
    if (!enabled) return;

    fetchData();
    const interval = setInterval(fetchData, pollInterval);
    return () => clearInterval(interval);
  }, [fetchData, pollInterval, enabled]);

  return { disks, history, availableDisks, loading, error, refetch: fetchData, lastUpdated };
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

  const [processes, setProcesses] = useState<Record<string, ProcessSample | null>>({});
  const [history, setHistory] = useState<Record<string, ProcessSample[]>>({});
  const [crashesDetected, setCrashesDetected] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [currentData, historyData] = await Promise.all([
        getProcessesCurrent(),
        getProcessesHistory(historyDuration, source, processName),
      ]);
      setProcesses(currentData.processes);
      setHistory(historyData.processes);
      setCrashesDetected(historyData.crashes_detected);
      setError(null);
      setLastUpdated(new Date());
    } catch (err: any) {
      setError(err.message || 'Failed to fetch process data');
    } finally {
      setLoading(false);
    }
  }, [historyDuration, source, processName]);

  useEffect(() => {
    if (!enabled) return;

    fetchData();
    const interval = setInterval(fetchData, pollInterval);
    return () => clearInterval(interval);
  }, [fetchData, pollInterval, enabled]);

  return { processes, history, crashesDetected, loading, error, refetch: fetchData, lastUpdated };
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
