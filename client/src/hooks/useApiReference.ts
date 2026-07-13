import { useState, useEffect, useMemo } from 'react';
import { buildApiUrl } from '../lib/api';
import type { ApiSection } from '../data/api-endpoints/types';
import type { ApiCategory } from '../lib/openapi-transform';
import type { RateLimitConfig } from '../lib/apiRateLimitMatch';
import { useOpenApiSchema } from './useOpenApiSchema';

export interface UseApiReferenceArgs {
  isAdmin: boolean;
  token: string | null;
}

export interface UseApiReferenceResult {
  activeView: 'docs' | 'limits';
  setActiveView: (v: 'docs' | 'limits') => void;
  selectedCategory: string | null;
  setSelectedCategory: (c: string | null) => void;
  selectedSection: string | null;
  setSelectedSection: (s: string | null) => void;
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  rateLimits: Record<string, RateLimitConfig>;
  loading: boolean;
  apiBaseUrl: string;
  apiSections: ApiSection[];
  apiCategories: ApiCategory[];
  schemaLoading: boolean;
  schemaError: string | null;
  refetchSchema: () => void;
  visibleSections: ApiSection[];
  currentCategorySections: ApiSection[];
}

export function useApiReference({ isAdmin, token }: UseApiReferenceArgs): UseApiReferenceResult {
  const [activeView, setActiveView] = useState<'docs' | 'limits'>('docs');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSection, setSelectedSection] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [rateLimits, setRateLimits] = useState<Record<string, RateLimitConfig>>({});
  const [loading, setLoading] = useState(true);

  const { sections: apiSections, categories: apiCategories, loading: schemaLoading, error: schemaError, refetch: refetchSchema } = useOpenApiSchema();

  // Dynamically determine API base URL based on current location
  const getApiBaseUrl = (): string => {
    const hostname = window.location.hostname;
    const isDev = import.meta.env.DEV;

    // In development, backend runs on port 3001
    // In production, backend typically runs on port 8000
    const port = isDev ? 3001 : 8000;
    const protocol = window.location.protocol; // http: or https:

    return `${protocol}//${hostname}:${port}`;
  };

  const apiBaseUrl = getApiBaseUrl();

  // Load rate limits for displaying badges (admin only)
  useEffect(() => {
    if (isAdmin) {
      loadRateLimits();
    } else {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  const loadRateLimits = async () => {
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(buildApiUrl('/api/admin/rate-limits'), {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        const map: Record<string, RateLimitConfig> = {};
        data.configs.forEach((c: RateLimitConfig) => {
          map[c.endpoint_type] = c;
        });
        setRateLimits(map);
      }
    } catch {
      // Rate limits not available
    } finally {
      setLoading(false);
    }
  };

  const visibleSections = useMemo(() => {
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return apiSections
        .map(s => ({
          ...s,
          endpoints: s.endpoints.filter(e =>
            e.path.toLowerCase().includes(q) ||
            e.description.toLowerCase().includes(q)
          ),
        }))
        .filter(s => s.endpoints.length > 0);
    }

    const categorySections = selectedCategory
      ? apiCategories.find(c => c.id === selectedCategory)?.sections ?? []
      : apiSections;

    return selectedSection
      ? categorySections.filter(s => s.title === selectedSection)
      : categorySections;
  }, [searchQuery, selectedCategory, selectedSection, apiSections, apiCategories]);

  const currentCategorySections = selectedCategory
    ? apiCategories.find(c => c.id === selectedCategory)?.sections ?? []
    : [];

  return {
    activeView, setActiveView, selectedCategory, setSelectedCategory,
    selectedSection, setSelectedSection, searchQuery, setSearchQuery,
    rateLimits, loading, apiBaseUrl,
    apiSections, apiCategories, schemaLoading, schemaError, refetchSchema,
    visibleSections, currentCategorySections,
  };
}
