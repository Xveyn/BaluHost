/**
 * Hook for getting current network I/O status
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import { getNetworkCurrent, type InterfaceType } from '../api/monitoring';
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

  // Shares queryKeys.monitoring.networkCurrent() with useNetworkMonitoring, so
  // mounting both (dashboard widget + system-monitor tab) collapses to a single
  // poll of the same endpoint.
  const query = useQuery({
    queryKey: queryKeys.monitoring.networkCurrent(),
    queryFn: getNetworkCurrent,
    refetchInterval: refreshInterval > 0 ? refreshInterval : false,
    enabled,
  });

  const data = query.data;
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
    loading: query.isLoading,
    error: query.error ? getApiErrorMessage(query.error, 'Failed to load network status') : null,
    refetch: async () => {
      await query.refetch();
    },
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
