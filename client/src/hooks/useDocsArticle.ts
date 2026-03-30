import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../lib/api';

export interface DocsArticle {
  content: string;
  title: string;
  slug: string;
  group: string;
}

export function useDocsArticle(slug: string | null) {
  const { i18n } = useTranslation();
  const lang = i18n.language?.split('-')[0] ?? 'de';

  const [article, setArticle] = useState<DocsArticle | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) {
      setArticle(null);
      setIsLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    apiClient
      .get<DocsArticle>(`/api/docs/article/${slug}`, { params: { lang } })
      .then((res) => {
        if (!cancelled) {
          setArticle(res.data);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.response?.data?.detail ?? 'Failed to load article');
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [slug, lang]);

  return { article, isLoading, error };
}
