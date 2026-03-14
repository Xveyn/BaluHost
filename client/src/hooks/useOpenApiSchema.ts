import { useState, useEffect, useCallback, useMemo } from 'react';
import { buildApiUrl } from '../lib/api';
import { transformOpenApi, type ApiCategory } from '../lib/openapi-transform';
import type { ApiSection } from '../data/api-endpoints/types';

const CACHE_KEY = 'baluhost_openapi_schema';

interface UseOpenApiSchemaResult {
  sections: ApiSection[];
  categories: ApiCategory[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useOpenApiSchema(): UseOpenApiSchemaResult {
  const [sections, setSections] = useState<ApiSection[]>([]);
  const [categories, setCategories] = useState<ApiCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const processSchema = useCallback((schema: unknown) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result = transformOpenApi(schema as any);
    setSections(result.sections);
    setCategories(result.categories);
    setError(null);
  }, []);

  const fetchSchema = useCallback(async (skipCache = false) => {
    setLoading(true);
    setError(null);

    // Try sessionStorage cache first
    if (!skipCache) {
      try {
        const cached = sessionStorage.getItem(CACHE_KEY);
        if (cached) {
          processSchema(JSON.parse(cached));
          setLoading(false);
          return;
        }
      } catch {
        // Cache miss or parse error, continue to fetch
      }
    }

    try {
      const response = await fetch(buildApiUrl('/openapi.json'));
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const schema = await response.json();

      // Cache in sessionStorage
      try {
        sessionStorage.setItem(CACHE_KEY, JSON.stringify(schema));
      } catch {
        // Storage full — non-critical
      }

      processSchema(schema);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load API schema');
    } finally {
      setLoading(false);
    }
  }, [processSchema]);

  useEffect(() => {
    fetchSchema();
  }, [fetchSchema]);

  const refetch = useCallback(() => {
    sessionStorage.removeItem(CACHE_KEY);
    fetchSchema(true);
  }, [fetchSchema]);

  return useMemo(() => ({
    sections,
    categories,
    loading,
    error,
    refetch,
  }), [sections, categories, loading, error, refetch]);
}
