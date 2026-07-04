import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { getDocsIndex } from '../api/docs';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';

// Re-exported so existing consumers (DocsSidebar, DocsOverview, DocsGroupTab)
// can keep importing the types from this hook.
export type { DocsArticleInfo, DocsGroupInfo } from '../api/docs';

/**
 * Documentation index (grouped articles) for the current UI language, via
 * TanStack Query. `lang` is part of the query key — switching language refetches.
 */
export function useDocsIndex() {
  const { i18n } = useTranslation();
  const lang = i18n.language?.split('-')[0] ?? 'de';

  const query = useQuery({
    queryKey: queryKeys.docs.index(lang),
    queryFn: () => getDocsIndex(lang),
  });

  return {
    groups: query.data ?? [],
    isLoading: query.isLoading,
    error: query.isError
      ? getApiErrorMessage(query.error, 'Failed to load documentation index')
      : null,
  };
}
