import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../lib/api';

export interface DocsArticleInfo {
  slug: string;
  title: string;
  icon: string;
}

export interface DocsGroupInfo {
  id: string;
  label: string;
  icon: string;
  articles: DocsArticleInfo[];
}

export function useDocsIndex() {
  const { i18n } = useTranslation();
  const lang = i18n.language?.split('-')[0] ?? 'de';

  const [groups, setGroups] = useState<DocsGroupInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    apiClient
      .get<{ groups: DocsGroupInfo[] }>('/api/docs/index', { params: { lang } })
      .then((res) => {
        if (!cancelled) {
          setGroups(res.data.groups);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.response?.data?.detail ?? 'Failed to load documentation index');
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [lang]);

  return { groups, isLoading, error };
}
