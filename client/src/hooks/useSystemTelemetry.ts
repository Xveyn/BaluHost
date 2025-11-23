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
  refreshing: boolean;
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

const TELEMETRY_CACHE_KEY = 'system_telemetry_cache';
const TELEMETRY_CACHE_DURATION = 120000; // 2 minutes

function getCachedTelemetry(): { system: SystemInfoResponse | null; storage: StorageInfoResponse | null; history: TelemetryHistory } | null {
  try {
    const cached = sessionStorage.getItem(TELEMETRY_CACHE_KEY);
    if (cached) {
      const data = JSON.parse(cached);
      const age = Date.now() - (data.timestamp || 0);
      if (age < TELEMETRY_CACHE_DURATION) {
        return { system: data.system, storage: data.storage, history: data.history };
      }
    }
  } catch (err) {
    console.error('Failed to read telemetry cache:', err);
  }
  return null;
}

function setCachedTelemetry(system: SystemInfoResponse, storage: StorageInfoResponse, history: TelemetryHistory): void {
  try {
    sessionStorage.setItem(TELEMETRY_CACHE_KEY, JSON.stringify({
      system,
      storage,
      history,
      timestamp: Date.now()
    }));
  } catch (err) {
    console.error('Failed to write telemetry cache:', err);
  }
}

export const useSystemTelemetry = (pollInterval = 5000): TelemetryState => {
  const cachedData = getCachedTelemetry();
  const [system, setSystem] = useState<SystemInfoResponse | null>(cachedData?.system || null);
  const [storage, setStorage] = useState<StorageInfoResponse | null>(cachedData?.storage || null);
  const [loading, setLoading] = useState<boolean>(!cachedData);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [history, setHistory] = useState<TelemetryHistory>(cachedData?.history || { cpu: [], memory: [], network: [] });
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('token');

    if (!token) {
      setError('Missing authentication token.');
      setLoading(false);
      return () => undefined;
    }

    let isMounted = true;

    const loadTelemetry = async (isInitial = false) => {
      try {
        // Set refreshing state for background updates
        if (!isInitial && (system || cachedData)) {
          setRefreshing(true);
        } else {
          setError(null);
        }
        
        const [infoRes, storageRes, historyRes] = await Promise.all([
          fetch(buildApiUrl('/api/system/info'), {
            headers: { Authorization: `Bearer ${token}` }
          }),
          fetch(buildApiUrl('/api/system/storage/aggregated'), {
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
        setCachedTelemetry(infoData, storageData, historyData);
        setLastUpdated(new Date());
        setLoading(false);
        setRefreshing(false);
      } catch (err: unknown) {
        if (!isMounted) {
          return;
        }

        const message = err instanceof Error ? err.message : 'Unexpected telemetry error';
        setError(message);
        setLoading(false);
        setRefreshing(false);
      }
    };

    // Load immediately - either initial load or background refresh
    if (!cachedData) {
      void loadTelemetry(true);
    } else {
      // With cache, immediately start background refresh
      setLoading(false);
      void loadTelemetry(false);
    }

    intervalRef.current = window.setInterval(() => {
      void loadTelemetry(false);
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
    refreshing,
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
