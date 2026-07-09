/**
 * Dev-only SMART data mode (mock vs. real) for the dashboard.
 *
 * Reads the server runtime mode and — only in dev mode — the current SMART
 * data source, then exposes a toggle. Query-backed (#299): keyed on
 * queryKeys.system.mode() + queryKeys.smart.mode(), so it shares one cache
 * entry / one fetch with every other consumer of those keys (e.g. the
 * scheduler MaintenancePanel) instead of a second hand-rolled fetch.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getSystemMode } from '../api/system';
import { getSmartMode, toggleSmartMode } from '../api/smart';

interface UseSmartModeReturn {
  smartMode: string | null;
  isDevMode: boolean;
  toggle: () => Promise<void>;
  isToggling: boolean;
}

export function useSmartMode(): UseSmartModeReturn {
  const queryClient = useQueryClient();

  const modeQuery = useQuery({
    queryKey: queryKeys.system.mode(),
    queryFn: getSystemMode,
    staleTime: Infinity, // dev/prod mode does not change within a session
  });
  const isDevMode = modeQuery.data?.dev_mode === true;

  const smartModeQuery = useQuery({
    queryKey: queryKeys.smart.mode(),
    queryFn: getSmartMode,
    enabled: isDevMode,
    // Mode only changes via toggle() (which republishes it through setQueryData),
    // so there is nothing to poll for — a stale time keeps co-mounted readers on
    // the one shared fetch instead of each refetching on mount.
    staleTime: 60_000,
  });

  const toggleMutation = useMutation({
    mutationFn: toggleSmartMode,
    onSuccess: (res) => {
      // Optimistically publish the new mode to the shared cache, then refresh
      // the SMART disk data (mock↔real changes what the status endpoint returns).
      queryClient.setQueryData(queryKeys.smart.mode(), res);
      void queryClient.invalidateQueries({ queryKey: queryKeys.smart.status() });
    },
  });

  return {
    smartMode: smartModeQuery.data?.mode ?? null,
    isDevMode,
    toggle: async () => {
      await toggleMutation.mutateAsync();
    },
    isToggling: toggleMutation.isPending,
  };
}
