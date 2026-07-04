/**
 * Hook for getting service status summary — TanStack Query backed.
 *
 * Mounted at three sites (ServicesPanel, Dashboard, ServiceSummaryWidget); the
 * shared query key collapses them into one cache entry + one poll instead of
 * three independent setInterval loops.
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import { getDebugSnapshot, type ServiceStatus, ServiceState } from '../api/service-status';

export interface ServicesSummary {
  running: number;
  stopped: number;
  error: number;
  disabled: number;
  total: number;
}

interface UseServicesSummaryOptions {
  refreshInterval?: number;
  enabled?: boolean;
}

interface UseServicesSummaryReturn {
  summary: ServicesSummary;
  services: ServiceStatus[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useServicesSummary(options: UseServicesSummaryOptions = {}): UseServicesSummaryReturn {
  const { refreshInterval = 30000, enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.services.summary(),
    queryFn: async () => (await getDebugSnapshot()).services,
    refetchInterval: refreshInterval > 0 ? refreshInterval : false,
    enabled,
  });

  const services = useMemo(() => query.data ?? [], [query.data]);

  const summary = useMemo<ServicesSummary>(() => {
    return {
      running: services.filter(s => s.state === ServiceState.RUNNING).length,
      stopped: services.filter(s => s.state === ServiceState.STOPPED).length,
      error: services.filter(s => s.state === ServiceState.ERROR).length,
      disabled: services.filter(s => s.state === ServiceState.DISABLED).length,
      total: services.length,
    };
  }, [services]);

  return {
    summary,
    services,
    loading: query.isLoading,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load services') : null,
    refetch: async () => {
      await query.refetch();
    },
  };
}
