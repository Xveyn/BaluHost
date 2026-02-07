import { useState, useEffect, useRef, useCallback } from 'react';
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

  // Ref to track pauseRefresh so in-flight API calls can check current value
  const pauseRefreshRef = useRef(pauseRefresh);
  pauseRefreshRef.current = pauseRefresh;

  const loadData = useCallback(async (isAutoRefresh = false) => {
    try {
      const [statusData, permData] = await Promise.all([
        getFanStatus(),
        getPermissionStatus()
      ]);

      // If this is an auto-refresh call and pause was activated while we were fetching,
      // discard the result to prevent overwriting user edits
      if (isAutoRefresh && pauseRefreshRef.current) return;

      setStatus(statusData);
      setPermissionStatus(permData);
      setError(null);
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Failed to load fan control';
      setError(message);
    }
  }, []);

  // Initial load - only once
  useEffect(() => {
    if (!enabled || hasLoadedOnce) return;

    setLoading(true);
    loadData(false).finally(() => {
      setLoading(false);
      setHasLoadedOnce(true);
    });
  }, [enabled, hasLoadedOnce, loadData]);

  // Auto-refresh - separate effect, no loading spinner
  useEffect(() => {
    if (!enabled || !hasLoadedOnce) return;
    if (refreshInterval <= 0 || pauseRefresh) return;

    const interval = setInterval(() => loadData(true), refreshInterval);
    return () => clearInterval(interval);
  }, [enabled, hasLoadedOnce, refreshInterval, pauseRefresh, loadData]);

  const isReadOnly = permissionStatus?.status === 'readonly';

  const refetch = useCallback(() => loadData(false), [loadData]);

  return {
    status,
    permissionStatus,
    loading,
    error,
    refetch,
    isReadOnly,
  };
}
