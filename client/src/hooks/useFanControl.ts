import { useState, useEffect } from 'react';
import { getFanStatus, getPermissionStatus } from '../api/fan-control';
import type { FanStatusResponse, PermissionStatusResponse } from '../api/fan-control';

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
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

  const loadData = async () => {
    try {
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
    }
  };

  // Initial load - only once
  useEffect(() => {
    if (!enabled || hasLoadedOnce) return;

    setLoading(true);
    loadData().finally(() => {
      setLoading(false);
      setHasLoadedOnce(true);
    });
  }, [enabled, hasLoadedOnce]);

  // Auto-refresh - separate effect, no loading spinner
  useEffect(() => {
    if (!enabled || !hasLoadedOnce) return;
    if (refreshInterval <= 0 || pauseRefresh) return;

    const interval = setInterval(loadData, refreshInterval);
    return () => clearInterval(interval);
  }, [enabled, hasLoadedOnce, refreshInterval, pauseRefresh]);

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
