import { useTranslation } from 'react-i18next';
import { RefreshCw } from 'lucide-react';
import { RateLimitsTab } from '../rate-limits';
import { useApiReference } from '../../hooks/useApiReference';
import {
  ApiViewToggle, ApiBaseUrlCard, ApiSearchBar, ApiCategoryTabs,
  ApiSchemaError, ApiLoadingSkeleton, ApiSectionList,
} from './api-reference';

export interface ApiReferenceTabProps {
  isAdmin: boolean;
  token: string | null;
}

export function ApiReferenceTab({ isAdmin, token }: ApiReferenceTabProps) {
  const { t } = useTranslation(['system', 'common']);
  const api = useApiReference({ isAdmin, token });

  return (
    <div className="space-y-4 sm:space-y-6">
      {isAdmin && (
        <ApiViewToggle activeView={api.activeView} onChange={api.setActiveView} t={t} />
      )}

      {api.activeView === 'limits' && isAdmin && <RateLimitsTab />}

      {api.activeView === 'docs' && <>
        {/* Refresh */}
        <div className="flex justify-end">
          <button
            onClick={api.refetchSchema}
            className="p-2 bg-slate-800/40 hover:bg-slate-700/60 border border-slate-700/50 rounded-lg transition-colors touch-manipulation active:scale-95"
            title="Refresh API schema"
          >
            <RefreshCw className={`w-4 h-4 text-slate-400 ${api.schemaLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {api.schemaError && <ApiSchemaError error={api.schemaError} onRetry={api.refetchSchema} />}

        <ApiBaseUrlCard apiBaseUrl={api.apiBaseUrl} t={t} />

        <ApiSearchBar value={api.searchQuery} onChange={api.setSearchQuery} t={t} />

        {!api.searchQuery.trim() && (
          <ApiCategoryTabs
            apiSections={api.apiSections}
            apiCategories={api.apiCategories}
            selectedCategory={api.selectedCategory}
            selectedSection={api.selectedSection}
            currentCategorySections={api.currentCategorySections}
            onSelectCategory={(id) => { api.setSelectedCategory(id); api.setSelectedSection(null); }}
            onSelectSection={api.setSelectedSection}
            t={t}
          />
        )}

        {(api.loading || api.schemaLoading) && <ApiLoadingSkeleton />}

        {!api.loading && !api.schemaLoading && (
          <ApiSectionList sections={api.visibleSections} rateLimits={api.rateLimits} t={t} />
        )}
      </>}
    </div>
  );
}
