import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, ChevronDown, ChevronRight, Code, X } from 'lucide-react';
import * as Icons from 'lucide-react';
import type { DocsGroupInfo } from '../../hooks/useDocsIndex';

interface DocsSidebarProps {
  groups: DocsGroupInfo[];
  activeArticle: string | null;
  activeTab: string;
  isAdmin: boolean;
  apiRefTabId: string;
  onSelectArticle: (groupId: string, slug: string) => void;
  onSelectApiRef: () => void;
  onClose?: () => void;
}

function getIcon(name: string, className = 'h-4 w-4'): React.ReactNode {
  const pascal = name
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const IconComp = (Icons as Record<string, any>)[pascal];
  if (IconComp) return <IconComp className={className} />;
  return <Icons.FileText className={className} />;
}

export default function DocsSidebar({
  groups,
  activeArticle,
  activeTab,
  isAdmin,
  apiRefTabId,
  onSelectArticle,
  onSelectApiRef,
  onClose,
}: DocsSidebarProps) {
  const { t } = useTranslation('manual');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    if (groups.length > 0) initial.add(groups[0].id);
    return initial;
  });

  // Auto-expand group containing the active article or matching the active tab
  useEffect(() => {
    const targetGroupId = activeArticle
      ? groups.find((g) => g.articles.some((a) => a.slug === activeArticle))?.id
      : activeTab && activeTab !== apiRefTabId
        ? activeTab
        : null;

    if (targetGroupId) {
      setExpandedGroups((prev) => {
        if (prev.has(targetGroupId)) return prev;
        return new Set([...prev, targetGroupId]);
      });
    }
  }, [activeArticle, activeTab, apiRefTabId, groups]);

  const toggleGroup = (groupId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  };

  const filteredGroups = useMemo(() => {
    if (!searchQuery.trim()) return groups;
    const q = searchQuery.toLowerCase();
    return groups
      .map((g) => ({
        ...g,
        articles: g.articles.filter((a) => a.title.toLowerCase().includes(q)),
      }))
      .filter((g) => g.articles.length > 0);
  }, [groups, searchQuery]);

  const isSearching = searchQuery.trim().length > 0;

  return (
    <div className="flex flex-col h-full">
      {/* Search */}
      <div className="p-3 border-b border-white/[0.06]">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('searchPlaceholder')}
            className="w-full pl-9 pr-8 py-2 rounded-xl border border-slate-800 bg-slate-900/70 text-sm text-slate-100 placeholder-slate-500 transition-all focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/40"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-slate-400 hover:text-white transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Navigation tree */}
      <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5">
        {filteredGroups.map((group) => {
          const isExpanded = expandedGroups.has(group.id) || isSearching;
          const hasActive = group.articles.some((a) => a.slug === activeArticle);

          return (
            <div key={group.id}>
              <button
                onClick={() => toggleGroup(group.id)}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 touch-manipulation ${
                  hasActive
                    ? 'text-sky-400 bg-sky-500/10 border border-sky-500/30'
                    : 'text-slate-300 hover:text-white border border-transparent'
                }`}
              >
                <span className="text-slate-500 flex-shrink-0">
                  {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                </span>
                <span className={`flex-shrink-0 ${hasActive ? 'text-sky-400' : 'text-slate-500'}`}>
                  {getIcon(group.icon)}
                </span>
                <span className="truncate flex-1 text-left">{group.label}</span>
                <span className="text-[10px] text-slate-600 tabular-nums flex-shrink-0">
                  {group.articles.length}
                </span>
              </button>

              {isExpanded && (
                <div className="ml-[22px] pl-3 border-l border-slate-700/30 space-y-px mt-1 mb-2">
                  {group.articles.map((article) => {
                    const isActive = activeArticle === article.slug;
                    return (
                      <button
                        key={article.slug}
                        onClick={() => {
                          onSelectArticle(group.id, article.slug);
                          onClose?.();
                        }}
                        className={`w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-[13px] transition-all duration-200 text-left touch-manipulation ${
                          isActive
                            ? 'bg-sky-500/15 text-sky-400 font-medium border border-sky-500/20'
                            : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04] border border-transparent'
                        }`}
                      >
                        <span className={`flex-shrink-0 ${isActive ? 'text-sky-400' : 'text-slate-500'}`}>
                          {getIcon(article.icon, 'h-3.5 w-3.5')}
                        </span>
                        <span className="truncate">{article.title}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}

        {/* API Reference (admin) */}
        {isAdmin && !isSearching && (
          <>
            <div className="my-2 mx-3 border-t border-white/[0.06]" />
            <button
              onClick={() => {
                onSelectApiRef();
                onClose?.();
              }}
              className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 touch-manipulation ${
                activeTab === apiRefTabId
                  ? 'text-sky-400 bg-sky-500/10 border border-sky-500/30'
                  : 'text-slate-300 hover:text-white border border-transparent'
              }`}
            >
              <span className="w-3.5 flex-shrink-0" />
              <Code className={`w-4 h-4 flex-shrink-0 ${activeTab === apiRefTabId ? 'text-sky-400' : 'text-slate-500'}`} />
              <span className="truncate">{t('tabs.api')}</span>
            </button>
          </>
        )}

        {/* No results */}
        {filteredGroups.length === 0 && isSearching && (
          <div className="text-center py-8 text-slate-500 text-sm">
            {t('noSearchResults')}
          </div>
        )}
      </nav>
    </div>
  );
}
