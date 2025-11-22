import { useEffect, useMemo, useRef, useState } from 'react';
import { buildApiUrl } from '../lib/api';

interface CpuInfo {
  usage: number;
  cores: number;
}

interface MemoryInfo {
  total: number;
  used: number;
  free: number;
}

interface DiskInfo {
  total: number;
  used: number;
  free: number;
}

interface SystemInfoResponse {
  cpu: CpuInfo;
  memory: MemoryInfo;
  disk: DiskInfo;
  uptime: number;
}

interface StorageInfoResponse {
  filesystem?: string;
  total: number;
  used: number;
  available: number;
  usePercent?: string | number;
  mountPoint?: string;
}

interface NormalisedStorageInfo extends StorageInfoResponse {
  percent: number;
}

interface CpuHistoryPoint {
  timestamp: number;
  usage: number;
}

interface MemoryHistoryPoint {
  timestamp: number;
  used: number;
  total: number;
  percent: number;
}

interface NetworkHistoryPoint {
  timestamp: number;
  downloadMbps: number;
  uploadMbps: number;
}

interface TelemetryHistory {
  cpu: CpuHistoryPoint[];
  memory: MemoryHistoryPoint[];
  network: NetworkHistoryPoint[];
}

interface TelemetryState {
  system: SystemInfoResponse | null;
  storage: NormalisedStorageInfo | null;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
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

export const useSystemTelemetry = (pollInterval = 5000): TelemetryState => {
  const [system, setSystem] = useState<SystemInfoResponse | null>(null);
  const [storage, setStorage] = useState<StorageInfoResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [history, setHistory] = useState<TelemetryHistory>({ cpu: [], memory: [], network: [] });
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('token');

    if (!token) {
      setError('Missing authentication token.');
      setLoading(false);
      return () => undefined;
    }

    let isMounted = true;

    const loadTelemetry = async () => {
      try {
        setError(null);
        const [infoRes, storageRes, historyRes] = await Promise.all([
          fetch(buildApiUrl('/api/system/info'), {
            headers: { Authorization: `Bearer ${token}` }
          }),
          fetch(buildApiUrl('/api/system/storage'), {
            headers: { Authorization: `Bearer ${token}` }
          }),
          fetch(buildApiUrl('/api/system/telemetry/history'), {
            headers: { Authorization: `Bearer ${token}` }
          })
        ]);

        if (!infoRes.ok) {
          throw new Error('Failed to fetch system info');
        }

        if (!storageRes.ok) {
          throw new Error('Failed to fetch storage info');
        }

        if (!historyRes.ok) {
          throw new Error('Failed to fetch telemetry history');
        }

        const infoData: SystemInfoResponse = await infoRes.json();
        const storageData: StorageInfoResponse = await storageRes.json();
        const historyData: TelemetryHistory = await historyRes.json();

        if (!isMounted) {
          return;
        }

        setSystem(infoData);
        setStorage(storageData);
        setHistory(historyData);
        setLastUpdated(new Date());
        setLoading(false);
      } catch (err: unknown) {
        if (!isMounted) {
          return;
        }

        const message = err instanceof Error ? err.message : 'Unexpected telemetry error';
        setError(message);
        setLoading(false);
      }
    };

    void loadTelemetry();

    intervalRef.current = window.setInterval(() => {
      void loadTelemetry();
    }, pollInterval);

    return () => {
      isMounted = false;
      if (intervalRef.current) {
        window.clearInterval(intervalRef.current);
      }
    };
  }, [pollInterval]);

  const normalisedStorage = useMemo<NormalisedStorageInfo | null>(() => {
    if (!storage) {
      return null;
    }

    const total = Number(storage.total) || 0;
    const used = Number(storage.used) || 0;
    const available = Number(storage.available) || Math.max(total - used, 0);
    const percent = total ? (used / total) * 100 : parsePercent(storage.usePercent);

    return {
      ...storage,
      total,
      used,
      available,
      percent: Math.min(Math.max(percent, 0), 100)
    };
  }, [storage]);

  return {
    system,
    storage: normalisedStorage,
    loading,
    error,
    lastUpdated,
    history
  };
};

export type {
  SystemInfoResponse,
  StorageInfoResponse,
  NormalisedStorageInfo,
  TelemetryHistory,
  CpuHistoryPoint,
  MemoryHistoryPoint,
  NetworkHistoryPoint
};
