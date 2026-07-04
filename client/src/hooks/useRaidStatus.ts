import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import { getRaidStatus, type RaidStatusResponse } from '../api/raid';

export interface UseRaidStatusResult {
  raidData: RaidStatusResponse | null;
  raidLoading: boolean;
  error: string | null;
  /** Timestamp of the last successful fetch (from `dataUpdatedAt`), null before the first. */
  lastUpdated: Date | null;
  /** Manual refetch; resolves to `true` on success, `false` if the refetch errored. */
  refetch: () => Promise<boolean>;
}

/**
 * RAID array status for the dashboard. Query-backed (persisted across F5 via the
 * app-wide persister); polls every `pollInterval` ms (default 60s).
 */
export function useRaidStatus(
  options: { pollInterval?: number; enabled?: boolean } = {}
): UseRaidStatusResult {
  const { pollInterval = 60000, enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.raid.status(),
    queryFn: getRaidStatus,
    refetchInterval: pollInterval,
    enabled,
  });

  return {
    raidData: query.data ?? null,
    raidLoading: query.isLoading,
    error: query.isError
      ? getApiErrorMessage(query.error, 'Failed to fetch RAID status')
      : null,
    lastUpdated: query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null,
    refetch: async () => {
      const res = await query.refetch();
      return !res.isError;
    },
  };
}
