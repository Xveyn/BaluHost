/**
 * Hook for getting service status summary (admin only)
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { getAllServices, type ServiceStatus, ServiceState } from '../api/service-status';

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

  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const response = await getAllServices();
      setServices(response);
      setError(null);
    } catch (err: any) {
      // Don't show error if user is not admin (403)
      if (err.response?.status === 403) {
        setServices([]);
        setError(null);
        return;
      }
      const message = err.response?.data?.detail || err.message || 'Failed to load services';
      setError(message);
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
    loading,
    error,
    refetch: loadData,
  };
}
