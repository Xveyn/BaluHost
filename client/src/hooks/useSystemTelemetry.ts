import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import {
  getSystemInfo,
  getAggregatedStorage,
  getTelemetryHistory,
  type SystemInfoResponse,
  type StorageInfoResponse,
  type TelemetryHistory,
  type CpuHistoryPoint,
  type MemoryHistoryPoint,
  type NetworkHistoryPoint,
} from '../api/system';

interface NormalisedStorageInfo extends StorageInfoResponse {
  percent: number;
}

interface TelemetryState {
  system: SystemInfoResponse | null;
  storage: NormalisedStorageInfo | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  lastUpdated: Date | null;
  history: TelemetryHistory;
}

interface TelemetrySnapshot {
  system: SystemInfoResponse;
  storage: StorageInfoResponse;
  history: TelemetryHistory;
}

const parsePercent = (value: string | number | undefined): number => {
  if (typeof value === 'number') {
    return value;
  }
  if (typeof value === 'string') {
    const cleaned = value.replace(/[^0-9.]/g, '');
    const parsed = Number.parseFloat(cleaned);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

export const useSystemTelemetry = (pollInterval = 15000): TelemetryState => {
  const { token } = useAuth();

  const query = useQuery({
    queryKey: queryKeys.system.telemetry(),
    queryFn: async (): Promise<TelemetrySnapshot> => {
      const [system, storage, history] = await Promise.all([
        getSystemInfo(),
        getAggregatedStorage(),
        getTelemetryHistory(),
      ]);
      return { system, storage, history };
    },
    refetchInterval: pollInterval,
    enabled: !!token,
  });

  const normalisedStorage = useMemo<NormalisedStorageInfo | null>(() => {
    const storage = query.data?.storage;
    if (!storage) {
      return null;
    }

    const total = Number(storage.total) || 0;
    const used = Number(storage.used) || 0;
    const available = Number(storage.available) || Math.max(total - used, 0);
    const percent = total ? (used / total) * 100 : parsePercent(storage.use_percent);

    return {
      ...storage,
      total,
      used,
      available,
      percent: Math.min(Math.max(percent, 0), 100),
    };
  }, [query.data?.storage]);

  return {
    system: query.data?.system ?? null,
    storage: normalisedStorage,
    loading: query.isLoading,
    refreshing: query.isFetching && !query.isLoading,
    error: query.isError
      ? getApiErrorMessage(query.error, 'Unexpected telemetry error')
      : null,
    lastUpdated: query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null,
    history: query.data?.history ?? { cpu: [], memory: [], network: [] },
  };
};

export type {
  SystemInfoResponse,
  StorageInfoResponse,
  NormalisedStorageInfo,
  TelemetryHistory,
  CpuHistoryPoint,
  MemoryHistoryPoint,
  NetworkHistoryPoint,
};
