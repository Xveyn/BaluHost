import { useState, useEffect, useCallback, useRef } from 'react';

interface UseAsyncDataOptions {
  /** Auto-refresh interval in milliseconds. Set to 0 or undefined to disable. */
  refreshInterval?: number;
  /** Whether the fetcher should run. Defaults to true. */
  enabled?: boolean;
}

interface UseAsyncDataResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Generic hook for fetching async data with loading/error states.
 *
 * Replaces the common pattern of:
 *   const [data, setData] = useState(null);
 *   const [loading, setLoading] = useState(true);
 *   const [error, setError] = useState(null);
 *   useEffect(() => { ... fetch ... }, []);
 */
export function useAsyncData<T>(
  fetcher: () => Promise<T>,
  options: UseAsyncDataOptions = {},
): UseAsyncDataResult<T> {
  const { refreshInterval, enabled = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const load = useCallback(async () => {
    try {
      setError(null);
      const result = await fetcherRef.current();
      setData(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An error occurred';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }

    load();

    if (refreshInterval && refreshInterval > 0) {
      const interval = setInterval(load, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [load, enabled, refreshInterval]);

  return { data, loading, error, refetch: load };
}
