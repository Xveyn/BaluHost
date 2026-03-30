import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { BookOpen, Code, Loader2 } from 'lucide-react';
import * as Icons from 'lucide-react';
import { useVersion } from '../contexts/VersionContext';
import { useAuth } from '../contexts/AuthContext';
import { useDocsIndex } from '../hooks/useDocsIndex';
import DocsGroupTab from '../components/manual/DocsGroupTab';
import { ApiReferenceTab } from '../components/manual/ApiReferenceTab';

const API_REF_TAB_ID = '__api-reference__';

function getTabIcon(name: string): React.ReactNode {
  const pascal = name
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const IconComp = (Icons as Record<string, any>)[pascal];
  if (IconComp) return <IconComp className="h-4 w-4" />;
  return <Icons.FileText className="h-4 w-4" />;
}

export default function UserManualPage() {
  const { t } = useTranslation(['manual', 'system', 'common']);
  const { version } = useVersion();
  const { token, isAdmin } = useAuth();
  const { groups, isLoading, error } = useDocsIndex();
  const [searchParams, setSearchParams] = useSearchParams();

  const rawTab = searchParams.get('tab') || '';
  const selectedArticle = searchParams.get('article') || null;

  const validTabIds = new Set(groups.map((g) => g.id));
  if (isAdmin) validTabIds.add(API_REF_TAB_ID);
  const activeTab = validTabIds.has(rawTab) ? rawTab : (groups[0]?.id ?? '');

  const handleTabChange = (tab: string) => {
    setSearchParams({ tab });
  };

  const handleSelectArticle = (slug: string | null) => {
    if (slug) {
      setSearchParams({ tab: activeTab, article: slug });
    } else {
      setSearchParams({ tab: activeTab });
    }
  };

  return (
    <div className="space-y-4 sm:space-y-6 p-4 sm:p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold bg-gradient-to-r from-cyan-400 via-blue-400 to-violet-400 bg-clip-text text-transparent flex items-center gap-2 sm:gap-3">
            <BookOpen className="w-6 h-6 sm:w-8 sm:h-8 text-cyan-400" />
            {t('manual:title')}
          </h1>
          <p className="text-slate-400 text-xs sm:text-sm mt-1">
            {t('manual:version', { version: version ?? '...' })}
          </p>
        </div>
        {version && (
          <span className="self-start sm:self-center inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
            v{version}
          </span>
        )}
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 text-cyan-400 animate-spin" />
        </div>
      )}

      {/* Error state */}
      {error && !isLoading && (
        <div className="text-center py-16 text-red-400 text-sm">{error}</div>
      )}

      {/* Tab Navigation + Content */}
      {!isLoading && !error && (
        <>
          <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
            <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
              {groups.map((group) => (
                <button
                  key={group.id}
                  onClick={() => handleTabChange(group.id)}
                  className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                    activeTab === group.id
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                      : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
                  }`}
                >
                  {getTabIcon(group.icon)}
                  <span>{group.label}</span>
                </button>
              ))}
              {isAdmin && (
                <button
                  onClick={() => handleTabChange(API_REF_TAB_ID)}
                  className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                    activeTab === API_REF_TAB_ID
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                      : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
                  }`}
                >
                  <Code className="h-4 w-4" />
                  <span>{t('manual:tabs.api')}</span>
                </button>
              )}
            </div>
          </div>

          {activeTab === API_REF_TAB_ID && isAdmin ? (
            <ApiReferenceTab isAdmin={isAdmin} token={token} />
          ) : (
            (() => {
              const activeGroup = groups.find((g) => g.id === activeTab);
              return activeGroup ? (
                <DocsGroupTab
                  group={activeGroup}
                  selectedArticle={selectedArticle}
                  onSelectArticle={handleSelectArticle}
                />
              ) : null;
            })()
          )}
        </>
      )}
    </div>
  );
}
