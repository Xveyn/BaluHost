import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getMobileDevices, type MobileDevice } from '../api/mobile';

export interface UseMobileDevicesResult {
  devices: MobileDevice[];
  loading: boolean;
  /** True during any fetch incl. background refetch — for the refresh spinner. */
  isFetching: boolean;
  refetch: () => Promise<unknown>;
}

/**
 * Registered mobile devices for MobileDevicesPage. Query-backed, polls every 10s
 * to reflect changes made from the mobile app. User-scoped (admins see all) —
 * AuthContext clears the cache on identity change.
 */
export function useMobileDevices(): UseMobileDevicesResult {
  const query = useQuery({
    queryKey: queryKeys.mobile.devices(),
    queryFn: getMobileDevices,
    refetchInterval: 10000,
  });

  return {
    devices: query.data ?? [],
    loading: query.isLoading,
    isFetching: query.isFetching,
    refetch: query.refetch,
  };
}
