import { useState, useEffect } from 'react';
import {
  getFanStatus,
  getPermissionStatus,
  FanStatusResponse,
  PermissionStatusResponse,
} from '../api/fan-control';

interface UseFanControlOptions {
  refreshInterval?: number;
  enabled?: boolean;
  pauseRefresh?: boolean;
}

interface UseFanControlReturn {
  status: FanStatusResponse | null;
  permissionStatus: PermissionStatusResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  isReadOnly: boolean;
}

export function useFanControl(options: UseFanControlOptions = {}): UseFanControlReturn {
  const { refreshInterval = 5000, enabled = true, pauseRefresh = false } = options;
  const [status, setStatus] = useState<FanStatusResponse | null>(null);
  const [permissionStatus, setPermissionStatus] = useState<PermissionStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);

      // Parallel fetch for faster loading
      const [statusData, permData] = await Promise.all([
        getFanStatus(),
        getPermissionStatus()
      ]);

      setStatus(statusData);
      setPermissionStatus(permData);
      setError(null);
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Failed to load fan control';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!enabled) return;

    loadData();

    // Only set up auto-refresh if not paused and interval > 0
    if (refreshInterval > 0 && !pauseRefresh) {
      const interval = setInterval(loadData, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [enabled, refreshInterval, pauseRefresh]);

  const isReadOnly = permissionStatus?.status === 'readonly';

  return {
    status,
    permissionStatus,
    loading,
    error,
    refetch: loadData,
    isReadOnly,
  };
}
