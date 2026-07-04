import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import { fetchSmartStatus } from '../api/smart';

/**
 * SMART disk health for the dashboard. Query-backed; polls every `pollingInterval`
 * ms (default 60s). The old hand-rolled localStorage cache is gone — F5 instant
 * paint now comes from the app-wide query persister (sessionStorage). Public shape
 * unchanged: { smartData, loading, error, lastUpdated, refetch }.
 */
export function useSmartData(pollingInterval = 60000) {
  const query = useQuery({
    queryKey: queryKeys.smart.status(),
    queryFn: fetchSmartStatus,
    refetchInterval: pollingInterval,
  });

  return {
    smartData: query.data ?? null,
    loading: query.isLoading,
    error: query.isError
      ? getApiErrorMessage(query.error, 'Fehler beim Laden der SMART-Daten')
      : null,
    lastUpdated: query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null,
    refetch: () => {
      void query.refetch();
    },
  };
}
