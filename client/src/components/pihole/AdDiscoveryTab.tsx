import { useState, useEffect, useCallback } from 'react';
import { Search, Activity, RefreshCw, AlertCircle, Code, Globe, List } from 'lucide-react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import { getAdDiscoveryStatus, startAnalysis, type AdDiscoveryStatus } from '../../api/adDiscovery';
import SuspectsTable from './ad-discovery/SuspectsTable';
import PatternsPanel from './ad-discovery/PatternsPanel';
import ReferenceListsPanel from './ad-discovery/ReferenceListsPanel';
import CustomListsPanel from './ad-discovery/CustomListsPanel';

type SubTab = 'suspects' | 'patterns' | 'reference-lists' | 'custom-lists';

export default function AdDiscoveryTab() {
  const { t } = useTranslation('pihole');
  const [status, setStatus] = useState<AdDiscoveryStatus | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [subTab, setSubTab] = useState<SubTab>('suspects');

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getAdDiscoveryStatus();
      setStatus(data);
    } catch {
      // Silently fail
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleAnalyze = async () => {
    setAnalyzing(true);
    try {
      const result = await startAnalysis();
      toast.success(
        t('adDiscovery.analysisComplete', {
          newCount: result.new_suspects,
          updatedCount: result.updated_suspects,
        })
      );
      fetchStatus();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || t('adDiscovery.analysisFailed'));
    } finally {
      setAnalyzing(false);
    }
  };

  const SUB_TABS: { key: SubTab; labelKey: string; icon: React.ReactNode }[] = [
    { key: 'suspects', labelKey: 'adDiscovery.subTabs.suspects', icon: <AlertCircle className="h-4 w-4" /> },
    { key: 'patterns', labelKey: 'adDiscovery.subTabs.patterns', icon: <Code className="h-4 w-4" /> },
    { key: 'reference-lists', labelKey: 'adDiscovery.subTabs.referenceLists', icon: <Globe className="h-4 w-4" /> },
    { key: 'custom-lists', labelKey: 'adDiscovery.subTabs.customLists', icon: <List className="h-4 w-4" /> },
  ];

  return (
    <div className="space-y-6">
      {/* Status Bar */}
      <div className="flex flex-wrap items-center gap-4 rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">{t('adDiscovery.newSuspects')}</span>
          <span className="font-semibold text-white">{status?.suspects_new ?? '—'}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">{t('adDiscovery.lastAnalysis')}</span>
          <span className="text-sm text-slate-300">
            {status?.last_analysis_at ? new Date(status.last_analysis_at).toLocaleString() : t('adDiscovery.never')}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">{t('adDiscovery.background')}</span>
          {status?.background_task_running ? (
            <span className="flex items-center gap-1 text-xs text-green-400">
              <Activity className="h-3 w-3" /> {t('adDiscovery.active')}
            </span>
          ) : (
            <span className="text-xs text-slate-500">{t('adDiscovery.inactive')}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">{t('adDiscovery.referenceLists')}</span>
          <span className="text-sm text-slate-300">
            {status?.reference_lists_active ?? 0}/{status?.reference_lists_total ?? 0}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">{t('adDiscovery.customLists')}</span>
          <span className="text-sm text-slate-300">
            {status?.custom_lists_total ?? 0} ({t('adDiscovery.customListsDeployed', { deployed: status?.custom_lists_deployed ?? 0 })})
          </span>
        </div>
        <div className="flex-1" />
        <button
          onClick={handleAnalyze}
          disabled={analyzing}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {analyzing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          {analyzing ? t('adDiscovery.analyzing') : t('adDiscovery.startAnalysis')}
        </button>
      </div>

      {/* Sub-Tab Navigation — pill style with blue accent, matching app standard */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
        <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
          {SUB_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setSubTab(tab.key)}
              className={`flex items-center gap-2 rounded-lg px-3 sm:px-4 py-2 text-xs sm:text-sm font-medium transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                subTab === tab.key
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                  : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
              }`}
            >
              {tab.icon}
              <span>{t(tab.labelKey)}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Sub-Tab Content */}
      {subTab === 'suspects' && <SuspectsTable />}
      {subTab === 'patterns' && <PatternsPanel />}
      {subTab === 'reference-lists' && <ReferenceListsPanel />}
      {subTab === 'custom-lists' && <CustomListsPanel />}
    </div>
  );
}
