/**
 * Hook for getting plugin status summary (admin only)
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
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

export function usePluginsSummary(options: UsePluginsSummaryOptions = {}): UsePluginsSummaryReturn {
  const { refreshInterval = 60000, enabled = true } = options;

  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const response = await listPlugins();
      setPlugins(response.plugins);
      setError(null);
    } catch (err: unknown) {
      // Don't show error if user is not admin (403)
      const status = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { status?: number } }).response?.status
        : undefined;
      if (status === 403) {
        setPlugins([]);
        setError(null);
        return;
      }
      setError(getApiErrorMessage(err, 'Failed to load plugins'));
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
    loading,
    error,
    refetch: loadData,
  };
}
