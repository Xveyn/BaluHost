import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { BookOpen, FileText, Loader2, Menu, X, ArrowLeft } from 'lucide-react';
import { useVersion } from '../contexts/VersionContext';
import { useAuth } from '../contexts/AuthContext';
import { useDocsIndex } from '../hooks/useDocsIndex';
import { useDocsArticle } from '../hooks/useDocsArticle';
import DocsSidebar from '../components/manual/DocsSidebar';
import ArticleView from '../components/manual/ArticleView';
import ArticleCard from '../components/manual/ArticleCard';
import DocsOverview from '../components/manual/DocsOverview';
import { ApiReferenceTab } from '../components/manual/ApiReferenceTab';

const API_REF_TAB_ID = '__api-reference__';

export default function UserManualPage() {
  const { t } = useTranslation(['manual', 'system', 'common']);
  const { version } = useVersion();
  const { token, isAdmin } = useAuth();
  const { groups, isLoading, error } = useDocsIndex();
  const [searchParams, setSearchParams] = useSearchParams();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const activeTab = searchParams.get('tab') || '';
  const selectedArticle = searchParams.get('article') || null;
  const isApiRef = activeTab === API_REF_TAB_ID && isAdmin;

  // A group is selected (tab set) but no article yet — show group articles
  const isGroupView = !!activeTab && !selectedArticle && !isApiRef;
  const activeGroup = isGroupView ? groups.find((g) => g.id === activeTab) : null;

  // Overview mode: no tab and no article selected
  const isOverview = !activeTab && !selectedArticle;

  const { article, isLoading: articleLoading, error: articleError } = useDocsArticle(selectedArticle);

  const handleSelectArticle = (groupId: string, slug: string) => {
    setSearchParams({ tab: groupId, article: slug });
  };

  const handleSelectGroup = (groupId: string) => {
    setSearchParams({ tab: groupId });
  };

  const handleSelectApiRef = () => {
    setSearchParams({ tab: API_REF_TAB_ID });
  };

  const handleBackToOverview = () => {
    setSearchParams({});
  };

  const handleBackToGroup = () => {
    if (activeTab && activeTab !== API_REF_TAB_ID) {
      setSearchParams({ tab: activeTab });
    } else {
      setSearchParams({});
    }
  };

  // Show sidebar only when browsing within a group or reading an article
  const showSidebar = !isOverview && (isGroupView || !!selectedArticle || isApiRef);

  return (
    <div className="space-y-4 sm:space-y-6 p-4 sm:p-6">
      {/* Header — only when not on overview (overview has its own hero) */}
      {!isOverview && (
        <div className="flex items-center gap-3">
          {/* Mobile sidebar toggle */}
          {showSidebar && (
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 hover:border-sky-500/50 hover:text-sky-400 transition touch-manipulation active:scale-95"
            >
              <Menu className="w-5 h-5" />
            </button>
          )}

          <div className="flex-1 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
            <div>
              <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold bg-gradient-to-r from-sky-400 via-blue-400 to-violet-400 bg-clip-text text-transparent flex items-center gap-2 sm:gap-3">
                <BookOpen className="w-6 h-6 sm:w-8 sm:h-8 text-sky-400" />
                {t('manual:title')}
              </h1>
              <p className="text-slate-400 text-xs sm:text-sm mt-1">
                {t('manual:version', { version: version ?? '...' })}
              </p>
            </div>
            {version && (
              <span className="self-start sm:self-center inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono bg-sky-500/10 text-sky-400 border border-sky-500/30">
                v{version}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 text-sky-400 animate-spin" />
        </div>
      )}

      {/* Error */}
      {error && !isLoading && (
        <div className="text-center py-16 text-red-400 text-sm">{error}</div>
      )}

      {/* Overview — full-width, no sidebar */}
      {!isLoading && !error && isOverview && (
        <DocsOverview
          groups={groups}
          version={version}
          onSelectGroup={handleSelectGroup}
        />
      )}

      {/* Main layout: Sidebar + Content (group view / article view / API ref) */}
      {!isLoading && !error && showSidebar && (
        <div className="flex gap-6 items-start">
          {/* Sidebar - Desktop (sticky, glass style) */}
          <aside className="hidden lg:block w-72 flex-shrink-0 sticky top-6 max-h-[calc(100vh-140px)] overflow-hidden rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.3),inset_0_1px_0_rgba(255,255,255,0.06)]">
            <DocsSidebar
              groups={groups}
              activeArticle={selectedArticle}
              activeTab={activeTab}
              isAdmin={isAdmin}
              apiRefTabId={API_REF_TAB_ID}
              onSelectArticle={handleSelectArticle}
              onSelectApiRef={handleSelectApiRef}
            />
          </aside>

          {/* Sidebar - Mobile (slide-in overlay) */}
          {sidebarOpen && (
            <>
              <div
                className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
                onClick={() => setSidebarOpen(false)}
              />
              <aside className="fixed left-0 top-0 bottom-0 z-50 w-72 bg-slate-900/95 backdrop-blur-3xl border-r border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.5)] lg:hidden flex flex-col">
                <div className="flex items-center justify-between px-4 pt-5 pb-3">
                  <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                    <BookOpen className="w-4 h-4 text-sky-400" />
                    {t('manual:navigation')}
                  </h2>
                  <button
                    onClick={() => setSidebarOpen(false)}
                    className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 hover:border-sky-500/50 hover:text-sky-400 transition touch-manipulation"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
                <DocsSidebar
                  groups={groups}
                  activeArticle={selectedArticle}
                  activeTab={activeTab}
                  isAdmin={isAdmin}
                  apiRefTabId={API_REF_TAB_ID}
                  onSelectArticle={handleSelectArticle}
                  onSelectApiRef={handleSelectApiRef}
                  onClose={() => setSidebarOpen(false)}
                />
              </aside>
            </>
          )}

          {/* Content area */}
          <main className="flex-1 min-w-0">
            {isApiRef ? (
              <div className="space-y-4">
                <button
                  onClick={handleBackToOverview}
                  className="flex items-center gap-2 text-sm text-slate-400 hover:text-sky-400 transition-colors touch-manipulation"
                >
                  <ArrowLeft className="h-4 w-4" />
                  {t('manual:backToOverview')}
                </button>
                <ApiReferenceTab isAdmin={isAdmin} token={token} />
              </div>
            ) : selectedArticle ? (
              articleLoading ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="h-8 w-8 text-sky-400 animate-spin" />
                </div>
              ) : articleError || !article ? (
                <div className="flex flex-col items-center justify-center py-16 text-slate-500">
                  <FileText className="h-12 w-12 mb-3 opacity-40" />
                  <p className="text-sm">{articleError ?? t('manual:errorLoading')}</p>
                </div>
              ) : (
                <ArticleView
                  content={article.content}
                  title={article.title}
                  onBack={handleBackToGroup}
                />
              )
            ) : activeGroup ? (
              /* Group view — show articles of selected group */
              <div className="space-y-4">
                <button
                  onClick={handleBackToOverview}
                  className="flex items-center gap-2 text-sm text-slate-400 hover:text-sky-400 transition-colors touch-manipulation"
                >
                  <ArrowLeft className="h-4 w-4" />
                  {t('manual:backToOverview')}
                </button>
                <h2 className="text-xl font-semibold text-white">
                  {activeGroup.label}
                </h2>
                {activeGroup.articles.length === 0 ? (
                  <p className="text-slate-500 text-sm">{t('manual:noArticles')}</p>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {activeGroup.articles.map((a) => (
                      <ArticleCard
                        key={a.slug}
                        title={a.title}
                        icon={a.icon}
                        onClick={() => handleSelectArticle(activeGroup.id, a.slug)}
                      />
                    ))}
                  </div>
                )}
              </div>
            ) : null}
          </main>
        </div>
      )}
    </div>
  );
}
