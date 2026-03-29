import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { BookOpen, Wrench, Library, Code } from 'lucide-react';
import { useVersion } from '../contexts/VersionContext';
import { useAuth } from '../contexts/AuthContext';
import SetupTab from '../components/manual/SetupTab';
import WikiTab from '../components/manual/WikiTab';
import { ApiReferenceTab } from '../components/manual/ApiReferenceTab';

type TabType = 'setup' | 'wiki' | 'api';

const VALID_TABS = new Set<TabType>(['setup', 'wiki', 'api']);

const TAB_CONFIG: { id: TabType; labelKey: string; icon: React.ReactNode }[] = [
  { id: 'setup', labelKey: 'manual:tabs.setup', icon: <Wrench className="h-4 w-4" /> },
  { id: 'wiki', labelKey: 'manual:tabs.wiki', icon: <Library className="h-4 w-4" /> },
  { id: 'api', labelKey: 'manual:tabs.api', icon: <Code className="h-4 w-4" /> },
];

export default function UserManualPage() {
  const { t } = useTranslation(['manual', 'system', 'common']);
  const { version } = useVersion();
  const { token, isAdmin } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const rawTab = searchParams.get('tab') || 'setup';
  const activeTab = (VALID_TABS.has(rawTab as TabType) ? rawTab : 'setup') as TabType;
  const selectedArticle = searchParams.get('article') || null;

  const handleTabChange = (tab: TabType) => {
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
        {/* Global version badge */}
        {version && (
          <span className="self-start sm:self-center inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
            v{version}
          </span>
        )}
      </div>

      {/* Tab Navigation */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
        <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
          {TAB_CONFIG.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                activeTab === tab.id
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                  : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
              }`}
            >
              {tab.icon}
              <span>{t(tab.labelKey)}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'setup' && (
        <SetupTab selectedArticle={selectedArticle} onSelectArticle={handleSelectArticle} />
      )}
      {activeTab === 'wiki' && (
        <WikiTab selectedArticle={selectedArticle} onSelectArticle={handleSelectArticle} />
      )}
      {activeTab === 'api' && (
        <ApiReferenceTab isAdmin={isAdmin} token={token} />
      )}
    </div>
  );
}
