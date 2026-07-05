import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getSleepStatus, type SleepStatusResponse } from '../api/sleep';
import { getFritzBoxConfig, type FritzBoxConfig } from '../api/fritzbox';

/**
 * Poll cadence for the sleep-status query: slow (30s) while in soft sleep so the
 * poll itself can't keep the box awake, fast (5s) otherwise. Pure so it can be
 * unit-tested without driving TanStack's scheduler.
 */
export function sleepPollInterval(state: string | undefined): number {
  return state === 'soft_sleep' ? 30000 : 5000;
}

interface UseSleepStatusReturn {
  status: SleepStatusResponse | null;
  loading: boolean;
  fbConfig: FritzBoxConfig | null;
  refetch: () => Promise<void>;
}

/**
 * Sleep-mode status via TanStack Query (#299). The `refetchInterval` is a
 * function so it adapts to the current state (see `sleepPollInterval`) —
 * replacing the old hand-rolled state-dependent setInterval. The Fritz!Box
 * config is a separate once-only query (`staleTime: Infinity`, no retry) so an
 * unconfigured box just yields `null` instead of retry spam. Errors on the
 * status poll are swallowed (TanStack keeps the last value), matching the old
 * silent-fail behavior. Mutations (enter/exit/suspend/WoL) stay imperative in
 * the panel and call `refetch`.
 */
export function useSleepStatus(): UseSleepStatusReturn {
  const statusQuery = useQuery({
    queryKey: queryKeys.sleep.status(),
    queryFn: getSleepStatus,
    refetchInterval: (query) => sleepPollInterval(query.state.data?.current_state),
  });

  const fritzQuery = useQuery({
    queryKey: queryKeys.sleep.fritzBox(),
    queryFn: getFritzBoxConfig,
    staleTime: Infinity,
    retry: false,
  });

  return {
    status: statusQuery.data ?? null,
    loading: statusQuery.isLoading,
    fbConfig: fritzQuery.data ?? null,
    refetch: async () => {
      await statusQuery.refetch();
    },
  };
}
