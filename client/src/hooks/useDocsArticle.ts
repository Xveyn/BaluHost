import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { getDocsArticle } from '../api/docs';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';

// Re-exported so existing consumers (UserManualPage, DocsGroupTab) can keep
// importing the type from this hook.
export type { DocsArticle } from '../api/docs';

/**
 * A single documentation article by slug, via TanStack Query. `slug`/`lang` are
 * part of the query key; a null slug disables the query (no fetch, article null).
 */
export function useDocsArticle(slug: string | null) {
  const { i18n } = useTranslation();
  const lang = i18n.language?.split('-')[0] ?? 'de';

  const query = useQuery({
    queryKey: queryKeys.docs.article(slug ?? '', lang),
    queryFn: () => getDocsArticle(slug as string, lang),
    enabled: !!slug,
  });

  return {
    article: query.data ?? null,
    isLoading: query.isLoading,
    error: query.isError ? getApiErrorMessage(query.error, 'Failed to load article') : null,
  };
}
