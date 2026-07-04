/**
 * Hook for getting plugin status summary (admin only) — TanStack Query backed.
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import { listPlugins, type PluginInfo } from '../api/plugins';

export interface PluginsSummary {
  total: number;
  enabled: number;
  disabled: number;
  withErrors: number;
}

interface UsePluginsSummaryOptions {
  refreshInterval?: number;
  enabled?: boolean;
}

interface UsePluginsSummaryReturn {
  summary: PluginsSummary;
  plugins: PluginInfo[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * Non-admins get a 403 from /api/plugins — treat that as "no plugins" silently
 * (unchanged from the pre-Query behavior) rather than surfacing an error.
 */
async function fetchPluginsSafe(): Promise<PluginInfo[]> {
  try {
    const response = await listPlugins();
    return response.plugins;
  } catch (err: unknown) {
    const status =
      err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { status?: number } }).response?.status
        : undefined;
    if (status === 403) return [];
    throw err;
  }
}

export function usePluginsSummary(options: UsePluginsSummaryOptions = {}): UsePluginsSummaryReturn {
  const { refreshInterval = 60000, enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.plugins.summary(),
    queryFn: fetchPluginsSafe,
    refetchInterval: refreshInterval > 0 ? refreshInterval : false,
    enabled,
  });

  const plugins = useMemo(() => query.data ?? [], [query.data]);

  const summary = useMemo<PluginsSummary>(() => {
    return {
      total: plugins.length,
      enabled: plugins.filter(p => p.is_enabled).length,
      disabled: plugins.filter(p => !p.is_enabled).length,
      withErrors: plugins.filter(p => p.error).length,
    };
  }, [plugins]);

  return {
    summary,
    plugins,
    loading: query.isLoading,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load plugins') : null,
    refetch: async () => {
      await query.refetch();
    },
  };
}
