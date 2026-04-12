/**
 * Hook for reading the server's runtime mode (dev vs. prod).
 * Fetches GET /api/system/mode once per browser session; result is cached at
 * module level so multiple consumers share a single request.
 */
import { useEffect, useState } from 'react';
import { apiClient } from '../lib/api';

export interface SystemMode {
  dev_mode: boolean;
}

// Module-level cache shared across all consumers of this hook.
let cachedMode: SystemMode | undefined;
let inflight: Promise<SystemMode> | undefined;

function loadSystemMode(): Promise<SystemMode> {
  if (cachedMode) return Promise.resolve(cachedMode);
  if (!inflight) {
    inflight = apiClient
      .get<SystemMode>('/api/system/mode')
      .then((res) => {
        cachedMode = res.data;
        return res.data;
      })
      .finally(() => {
        inflight = undefined;
      });
  }
  return inflight;
}

export function useSystemMode() {
  const [data, setData] = useState<SystemMode | undefined>(cachedMode);
  const [loading, setLoading] = useState<boolean>(!cachedMode);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (cachedMode) {
      // Already loaded by a previous render of some other component
      setData(cachedMode);
      setLoading(false);
      return;
    }
    let cancelled = false;
    loadSystemMode()
      .then((mode) => {
        if (!cancelled) {
          setData(mode);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e : new Error(String(e)));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { data, loading, error };
}
