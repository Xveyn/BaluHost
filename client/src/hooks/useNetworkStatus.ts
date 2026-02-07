/**
 * Hook for getting current network I/O status
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { getNetworkCurrent, type CurrentNetworkResponse, type InterfaceType } from '../api/monitoring';
import { formatNumber } from '../lib/formatters';

export interface NetworkStatus {
  downloadMbps: number;
  uploadMbps: number;
  timestamp: Date;
  interfaceType: InterfaceType;
}

interface UseNetworkStatusOptions {
  refreshInterval?: number;
  enabled?: boolean;
}

interface UseNetworkStatusReturn {
  status: NetworkStatus | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useNetworkStatus(options: UseNetworkStatusOptions = {}): UseNetworkStatusReturn {
  const { refreshInterval = 3000, enabled = true } = options;

  const [data, setData] = useState<CurrentNetworkResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const response = await getNetworkCurrent();
      setData(response);
      setError(null);
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Failed to load network status';
      setError(message);
    }
  }, []);

  // Initial load
  useEffect(() => {
    if (!enabled) return;

    setLoading(true);
    loadData().finally(() => setLoading(false));
  }, [enabled, loadData]);

  // Auto-refresh
  useEffect(() => {
    if (!enabled || refreshInterval <= 0) return;

    const interval = setInterval(loadData, refreshInterval);
    return () => clearInterval(interval);
  }, [enabled, refreshInterval, loadData]);

  const status = useMemo<NetworkStatus | null>(() => {
    if (!data) return null;

    return {
      downloadMbps: data.download_mbps,
      uploadMbps: data.upload_mbps,
      timestamp: new Date(data.timestamp),
      interfaceType: data.interface_type || 'unknown',
    };
  }, [data]);

  return {
    status,
    loading,
    error,
    refetch: loadData,
  };
}

// Helper: format Mbps with appropriate unit
export function formatNetworkSpeed(mbps: number): string {
  if (mbps < 0.01) {
    return '0 Mbps';
  }
  if (mbps < 1) {
    return `${formatNumber(mbps * 1000, 0)} Kbps`;
  }
  if (mbps < 100) {
    return `${formatNumber(mbps, 1)} Mbps`;
  }
  if (mbps < 1000) {
    return `${formatNumber(mbps, 0)} Mbps`;
  }
  return `${formatNumber(mbps / 1000, 2)} Gbps`;
}
