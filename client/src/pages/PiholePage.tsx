import { useState, useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  WifiOff,
  LayoutDashboard,
  ListOrdered,
  BarChart3,
  History,
  Search,
  Globe,
  ShieldOff,
  Server,
  Settings as SettingsIcon,
  Terminal,
} from 'lucide-react';
import {
  getPiholeStatus,
  getPiholeSummary,
  setBlocking,
  getTopDomains,
  getTopBlocked,
  getTopClients,
  getHistory,
  type PiholeStatus,
  type PiholeSummary,
  type DomainEntry,
  type ClientEntry,
  type HistoryEntry,
} from '../api/pihole';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import PiholeStatusBar from '../components/pihole/PiholeStatusBar';
import PiholeSummaryCards from '../components/pihole/PiholeSummaryCards';
import PiholeQueryTimeline from '../components/pihole/PiholeQueryTimeline';
import PiholeQueryLog from '../components/pihole/PiholeQueryLog';
import TopDomainsPanel from '../components/pihole/TopDomainsPanel';
import TopClientsPanel from '../components/pihole/TopClientsPanel';
import PiholeDomainManagement from '../components/pihole/PiholeDomainManagement';
import PiholeAdlistManagement from '../components/pihole/PiholeAdlistManagement';
import PiholeLocalDns from '../components/pihole/PiholeLocalDns';
import PiholeSettings from '../components/pihole/PiholeSettings';
import PiholeContainerActions from '../components/pihole/PiholeContainerActions';
import PiholeAnalytics from '../components/pihole/PiholeAnalytics';
import PiholeStoredQueryLog from '../components/pihole/PiholeStoredQueryLog';
import QueryCollectorStatus from '../components/pihole/QueryCollectorStatus';
import AdDiscoveryTab from '../components/pihole/AdDiscoveryTab';

type Tab =
  | 'overview'
  | 'queries'
  | 'analytics'
  | 'stored-queries'
  | 'ad-discovery'
  | 'domains'
  | 'adlists'
  | 'dns'
  | 'settings'
  | 'container';

interface TabConfig {
  key: Tab;
  labelKey: string;
  icon: React.ReactNode;
}

const TABS: TabConfig[] = [
  { key: 'overview', labelKey: 'tabs.overview', icon: <LayoutDashboard className="h-4 w-4" /> },
  { key: 'queries', labelKey: 'tabs.queryLog', icon: <ListOrdered className="h-4 w-4" /> },
  { key: 'analytics', labelKey: 'tabs.analytics', icon: <BarChart3 className="h-4 w-4" /> },
  { key: 'stored-queries', labelKey: 'tabs.queryHistory', icon: <History className="h-4 w-4" /> },
  { key: 'ad-discovery', labelKey: 'tabs.adDiscovery', icon: <Search className="h-4 w-4" /> },
  { key: 'domains', labelKey: 'tabs.domains', icon: <Globe className="h-4 w-4" /> },
  { key: 'adlists', labelKey: 'tabs.adlists', icon: <ShieldOff className="h-4 w-4" /> },
  { key: 'dns', labelKey: 'tabs.localDns', icon: <Server className="h-4 w-4" /> },
  { key: 'settings', labelKey: 'tabs.settings', icon: <SettingsIcon className="h-4 w-4" /> },
  { key: 'container', labelKey: 'tabs.container', icon: <Terminal className="h-4 w-4" /> },
];

interface PiholeOverview {
  status: PiholeStatus;
  summary: PiholeSummary | null;
  topPermitted: DomainEntry[];
  topBlocked: DomainEntry[];
  topClients: ClientEntry[];
  history: HistoryEntry[];
  /** True when status loaded but the statistics fan-out failed. */
  statsError: boolean;
  statsErrorMsg: string;
}

/**
 * Aggregate overview fetch (#299) — one query replaces the old 30s setInterval.
 * A statistics-fan-out failure does NOT reject (status still renders); it is
 * surfaced via `statsError`. A status failure rejects → the query goes to error.
 */
async function fetchPiholeOverview(): Promise<PiholeOverview> {
  const status = await getPiholeStatus();
  const empty = { summary: null, topPermitted: [], topBlocked: [], topClients: [], history: [] };
  if (!status.connected) {
    return { status, ...empty, statsError: false, statsErrorMsg: '' };
  }
  try {
    const [summaryData, domainsData, blockedData, clientsData, historyData] = await Promise.all([
      getPiholeSummary(),
      getTopDomains(10),
      getTopBlocked(10),
      getTopClients(10),
      getHistory(),
    ]);
    return {
      status,
      summary: summaryData,
      topPermitted: domainsData.top_permitted,
      topBlocked: blockedData.top_blocked,
      topClients: clientsData.top_clients,
      history: historyData.history,
      statsError: false,
      statsErrorMsg: '',
    };
  } catch (err) {
    return { status, ...empty, statsError: true, statsErrorMsg: getApiErrorMessage(err, '') };
  }
}

export default function PiholePage() {
  const { t } = useTranslation('pihole');
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>('overview');

  // Query-backed (#299): the single 30s aggregate poll. `isLoading` gates the
  // first-load skeletons only (the old code flashed them on every poll).
  const { data, isLoading: loading, isError, error } = useQuery({
    queryKey: queryKeys.pihole.overview(),
    queryFn: fetchPiholeOverview,
    refetchInterval: 30000,
  });

  const status = data?.status ?? null;
  const summary = data?.summary ?? null;
  const topPermitted = data?.topPermitted ?? [];
  const topBlocked = data?.topBlocked ?? [];
  const topClients = data?.topClients ?? [];
  const history = data?.history ?? [];
  const fetchError = isError;

  // Toast once per error-onset (not on every poll like the old code). Preserves
  // the FastAPI detail via getApiErrorMessage.
  const prevFetchError = useRef(false);
  useEffect(() => {
    if (isError && !prevFetchError.current) {
      toast.error(getApiErrorMessage(error, t('states.loadFailedData')));
    }
    prevFetchError.current = isError;
  }, [isError, error, t]);

  const statsError = data?.statsError ?? false;
  const prevStatsError = useRef(false);
  useEffect(() => {
    if (statsError && !prevStatsError.current) {
      toast.error(data?.statsErrorMsg || t('states.loadFailedStatistics'));
    }
    prevStatsError.current = statsError;
  }, [statsError, data?.statsErrorMsg, t]);

  const blockingMutation = useMutation({
    mutationFn: (enabled: boolean) => setBlocking(enabled),
    onSuccess: (_res, enabled) => {
      // Optimistically patch the cached status so the toggle reflects immediately.
      queryClient.setQueryData<PiholeOverview>(queryKeys.pihole.overview(), (prev) =>
        prev ? { ...prev, status: { ...prev.status, blocking_enabled: enabled } } : prev,
      );
      toast.success(enabled ? t('status.blockingOn') : t('status.blockingOff'));
    },
    onError: (err) => toast.error(getApiErrorMessage(err, t('status.blockingToggleFailed'))),
  });
  const handleBlockingToggle = (enabled: boolean) => blockingMutation.mutate(enabled);

  const unreachableMessage =
    status?.mode === 'docker'
      ? t('states.unreachableDocker')
      : status?.mode === 'remote'
        ? t('states.unreachableRemote')
        : t('states.unreachableGeneric');

  return (
    <div className="space-y-6 min-w-0">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('title')}</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">{t('description')}</p>
        </div>
      </div>

      {/* Disabled State */}
      {status && status.mode === 'disabled' && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-6">
          <div className="flex items-start gap-4">
            <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0 text-amber-400" />
            <div>
              <h3 className="text-lg font-medium text-amber-200">{t('states.disabledTitle')}</h3>
              <p className="mt-1 text-sm text-slate-400">
                {t('states.disabledMessage')}{' '}
                <button
                  onClick={() => setActiveTab('settings')}
                  className="text-blue-400 underline hover:text-blue-300"
                >
                  {t('states.settingsLink')}
                </button>
                {t('states.disabledTrailing')}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Unreachable State */}
      {(fetchError || (status && !status.connected && status.mode !== 'disabled')) && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-6">
          <div className="flex items-start gap-4">
            <WifiOff className="mt-0.5 h-6 w-6 flex-shrink-0 text-red-400" />
            <div>
              <h3 className="text-lg font-medium text-red-200">{t('states.unreachableTitle')}</h3>
              <p className="mt-1 text-sm text-slate-400">
                {unreachableMessage}{' '}
                <button
                  onClick={() => setActiveTab('settings')}
                  className="text-blue-400 underline hover:text-blue-300"
                >
                  {t('states.settingsLink')}
                </button>
                .
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Status Bar */}
      {status && status.mode !== 'disabled' && (
        <PiholeStatusBar status={status} onBlockingToggle={handleBlockingToggle} loading={loading} />
      )}

      {/* Tab Navigation — pill style with icons + blue accent, matching SystemControl/Scheduler */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
        <div className="flex gap-2 border-b border-slate-800 pb-3 min-w-max sm:min-w-0 sm:flex-wrap">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 rounded-lg px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm font-medium transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                activeTab === tab.key
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

      {/* Tab Content */}
      <div className="min-w-0">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            <PiholeSummaryCards summary={summary} loading={loading} />
            <PiholeQueryTimeline history={history} loading={loading} />
            <div className="grid gap-6 lg:grid-cols-2">
              <TopDomainsPanel topPermitted={topPermitted} topBlocked={topBlocked} loading={loading} />
              <TopClientsPanel clients={topClients} loading={loading} />
            </div>
          </div>
        )}

        {activeTab === 'queries' && <PiholeQueryLog />}
        {activeTab === 'analytics' && <PiholeAnalytics />}
        {activeTab === 'stored-queries' && <PiholeStoredQueryLog />}
        {activeTab === 'ad-discovery' && <AdDiscoveryTab />}
        {activeTab === 'domains' && <PiholeDomainManagement />}
        {activeTab === 'adlists' && <PiholeAdlistManagement />}
        {activeTab === 'dns' && <PiholeLocalDns />}

        {activeTab === 'settings' && (
          <div className="space-y-6">
            <PiholeSettings />
            <QueryCollectorStatus />
          </div>
        )}

        {activeTab === 'container' && <PiholeContainerActions />}
      </div>
    </div>
  );
}
