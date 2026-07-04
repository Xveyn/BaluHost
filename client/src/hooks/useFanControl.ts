import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
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

/**
 * Fan status + write-permission for the fan-control page. Query-backed (#299):
 * `refetchInterval` replaces the old hand-rolled setInterval. Polling pauses
 * while `pauseRefresh` is set (the page pauses it while a curve is being edited)
 * and never runs the loading spinner past the first load.
 *
 * Preserves the old "don't flash 'no fans'" guard: a transient empty response is
 * masked by the last non-empty status (covers hwmon scan blips / follower workers
 * without a backend).
 */
export function useFanControl(options: UseFanControlOptions = {}): UseFanControlReturn {
  const { refreshInterval = 5000, enabled = true, pauseRefresh = false } = options;

  const query = useQuery({
    queryKey: queryKeys.fans.control(),
    queryFn: async () => {
      const [status, permission] = await Promise.all([getFanStatus(), getPermissionStatus()]);
      return { status, permission };
    },
    enabled,
    refetchInterval: !pauseRefresh && refreshInterval > 0 ? refreshInterval : false,
  });

  // Mask a transient empty fan list with the last non-empty snapshot.
  const lastNonEmptyRef = useRef<FanStatusResponse | null>(null);
  const rawStatus = query.data?.status ?? null;
  if (rawStatus && rawStatus.fans.length > 0) {
    lastNonEmptyRef.current = rawStatus;
  }
  const status =
    rawStatus && rawStatus.fans.length === 0 && lastNonEmptyRef.current
      ? lastNonEmptyRef.current
      : rawStatus;

  const permissionStatus = query.data?.permission ?? null;

  return {
    status,
    permissionStatus,
    loading: query.isLoading,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load fan control') : null,
    refetch: async () => {
      await query.refetch();
    },
    isReadOnly: permissionStatus?.status === 'readonly',
  };
}
