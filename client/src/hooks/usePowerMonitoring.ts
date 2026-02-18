/**
 * Custom hook for power monitoring data
 *
 * Polls power data every 5 seconds with automatic cleanup.
 * Follows the pattern from useSystemTelemetry.
 */

import { useState, useEffect, useCallback } from 'react';
import { getPowerHistory } from '../api/power';
import type { PowerMonitoringResponse } from '../api/power';

const POLL_INTERVAL = 5000; // 5 seconds

interface UsePowerMonitoringReturn {
  data: PowerMonitoringResponse | null;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  refetch: () => Promise<void>;
}

export function usePowerMonitoring(): UsePowerMonitoringReturn {
  const [data, setData] = useState<PowerMonitoringResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const response = await getPowerHistory();
      setData(response);
      setError(null);
      setLastUpdated(new Date());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch power data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial fetch
    fetchData();

    // Set up polling interval
    const intervalId = setInterval(() => {
      fetchData();
    }, POLL_INTERVAL);

    // Cleanup on unmount
    return () => {
      clearInterval(intervalId);
    };
  }, [fetchData]);

  return {
    data,
    loading,
    error,
    lastUpdated,
    refetch: fetchData,
  };
}
